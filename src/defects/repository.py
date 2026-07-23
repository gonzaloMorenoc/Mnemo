from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from pgvector import Vector
from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.config import DATABASE_URL
from src.db.pool import get_pool
from src.defects.centroid import update_centroid
from src.defects.match import FamilyCandidate, decide_match
from src.ingest.models import FailureRecord
from src.triage.dom import dom_changed

_CI_STATUSES = ("pass", "fail", "flaky", "skipped")
_CI_KINDS = ("last_green", "failure")


@dataclass
class IngestItem:
    rec: FailureRecord
    fingerprint: str
    embedding: Sequence[float]
    external_ref: Optional[str] = None
    external_url: Optional[str] = None


class AssuranceRepository:
    """Persistence layer for Mnemo assurance data (test runs, failures, defect families).

    The session pooler connects as a superuser role that bypasses RLS.
    Isolation is therefore enforced at the application layer via explicit
    membership checks — never remove those checks.
    """

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def _set_claims(self, conn: psycopg.Connection, user_id: str) -> None:
        """Propaga el claim del usuario. NOTA: el rol del pooler hace BYPASS de RLS,
        asi que esto es scaffolding para el futuro (conexion via rol authenticated);
        el aislamiento real lo hacen los filtros por membership de cada query."""
        with conn.cursor() as cur:
            cur.execute(
                "select set_config('request.jwt.claim.sub', %s, true)",
                (user_id,),
            )
            cur.execute(
                "select set_config('request.jwt.claim.role', 'authenticated', true)"
            )

    def _query_candidates(
        self,
        cur: psycopg.Cursor,
        *,
        org_id: str,
        fingerprint: str,
        embedding: Sequence[float],
        limit: int = 10,
    ) -> List[FamilyCandidate]:
        # Incluye SIEMPRE la familia con la firma exacta (aunque su centroide haya
        # derivado fuera del top-K por coseno) para no crear familias duplicadas,
        # mas el top-K por coseno para el matching semantico.
        cur.execute(
            """
            select id, signature, centroid
            from public.defect_families
            where scope = 'org' and org_id = %(org)s
              and (
                  signature = %(fp)s
                  or id in (
                      select id from public.defect_families
                      where scope = 'org' and org_id = %(org)s and centroid is not null
                      order by centroid <=> %(emb)s
                      limit %(k)s
                  )
              )
            """,
            {"org": org_id, "fp": fingerprint, "emb": Vector(list(embedding)), "k": limit},
        )
        rows = cur.fetchall()
        return [
            FamilyCandidate(
                family_id=str(r["id"]),
                signature=r["signature"],
                centroid=list(r["centroid"]) if r["centroid"] is not None else None,
            )
            for r in rows
        ]

    def _match_and_insert_failure(self, cur, *, org_id: str, run_id, item: IngestItem) -> bool:
        """Empareja un fallo con su familia (crea o actualiza centroide/contador) e inserta
        la fila de `failures`. Devuelve True si la familia es nueva (novel), False si conocida.
        Debe ejecutarse dentro de una transacción abierta (recibe el cursor)."""
        cands = self._query_candidates(
            cur, org_id=org_id, fingerprint=item.fingerprint, embedding=item.embedding
        )
        decision = decide_match(
            fingerprint=item.fingerprint, embedding=item.embedding, candidates=cands,
        )
        if decision.is_new:
            title = item.rec.error_type or item.rec.message[:80] or "unknown"
            cur.execute(
                """
                insert into public.defect_families
                    (scope, org_id, signature, title, occurrence_count, centroid)
                values ('org', %s, %s, %s, 1, %s)
                returning id
                """,
                (org_id, item.fingerprint, title, Vector(list(item.embedding))),
            )
            family_id = cur.fetchone()["id"]
            is_new = True
        else:
            family_id = decision.family_id
            cur.execute(
                "select occurrence_count, centroid"
                " from public.defect_families where id = %s for update",
                (family_id,),
            )
            fam = cur.fetchone()
            new_centroid = update_centroid(
                list(fam["centroid"]) if fam["centroid"] is not None else None,
                fam["occurrence_count"], list(item.embedding),
            )
            cur.execute(
                """
                update public.defect_families
                set occurrence_count = occurrence_count + 1, last_seen = now(), centroid = %s
                where id = %s
                """,
                (Vector(new_centroid), family_id),
            )
            is_new = False
        cur.execute(
            """
            insert into public.failures
                (run_id, org_id, test_name, error_type, message, trace,
                 fingerprint, embedding, sanitized, defect_family_id,
                 external_ref, external_url, file, line)
            values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s, %s)
            """,
            (run_id, org_id, item.rec.test_name, item.rec.error_type, item.rec.message,
             item.rec.trace, item.fingerprint, Vector(list(item.embedding)), family_id,
             item.external_ref, item.external_url, item.rec.file, item.rec.line),
        )
        return is_new

    def _insert_run_or_get_existing(
        self,
        cur,
        *,
        org_id: str,
        project: str,
        source: str,
        commit_sha: Optional[str],
        run_uid: Optional[str],
    ):
        """Inserta el test_run del ingest. Si run_uid viene y ya existe (org_id, run_uid)
        — entrega duplicada concurrente o reintento — devuelve el run existente con su
        summary en vez de insertar. Devuelve (run_id, existing_summary | None); summary
        None significa "run recién creado". Debe ejecutarse dentro de la transacción."""
        if run_uid is None:
            cur.execute(
                "insert into public.test_runs (org_id, project, source, commit_sha)"
                " values (%s, %s, %s, %s) returning id",
                (org_id, project, source, commit_sha),
            )
            return cur.fetchone()["id"], None
        cur.execute(
            "insert into public.test_runs (org_id, project, source, commit_sha, run_uid)"
            " values (%s, %s, %s, %s, %s)"
            " on conflict (org_id, run_uid) where run_uid is not null do nothing"
            " returning id",
            (org_id, project, source, commit_sha, run_uid),
        )
        inserted = cur.fetchone()
        if inserted is not None:
            return inserted["id"], None
        cur.execute(
            "select id, summary from public.test_runs"
            " where org_id = %s and run_uid = %s",
            (org_id, run_uid),
        )
        existing = cur.fetchone()
        return existing["id"], (existing["summary"] or {})

    def ingest_run(
        self,
        *,
        user_id: str,
        org_id: str,
        project: str,
        source: str,
        items: List[IngestItem],
        commit_sha: Optional[str] = None,
        run_uid: Optional[str] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ingest a test run and classify each failure into a defect family.

        Idempotente por (org_id, run_uid) si run_uid viene: un re-upload del mismo
        reporte devuelve el run existente con deduplicated=True en vez de crear otro
        run y doblar occurrence_count de las familias.

        Returns a dict with keys: run_id, ingested, known, novel, deduplicated.
        Raises PermissionError if the user is not a member of the org.
        """
        known = 0
        novel = 0

        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                # App-layer isolation: pooler role bypasses RLS, so we enforce
                # membership explicitly here.
                cur.execute(
                    "select exists("
                    "  select 1 from public.memberships"
                    "  where org_id = %s and user_id = %s"
                    ") as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")

                run_id, existing_summary = self._insert_run_or_get_existing(
                    cur, org_id=org_id, project=project, source=source,
                    commit_sha=commit_sha, run_uid=run_uid,
                )
                if existing_summary is not None:
                    return {
                        "run_id": str(run_id),
                        "ingested": existing_summary.get("ingested", 0),
                        "known": existing_summary.get("known", 0),
                        "novel": existing_summary.get("novel", 0),
                        "deduplicated": True,
                    }

                for item in items:
                    if self._match_and_insert_failure(cur, org_id=org_id, run_id=run_id, item=item):
                        novel += 1
                    else:
                        known += 1

                summary = {"ingested": len(items), "known": known, "novel": novel}
                if manifest is not None:
                    summary["manifest"] = manifest
                cur.execute(
                    "update public.test_runs set summary = %s where id = %s",
                    (Json(summary), run_id),
                )

            conn.commit()

        return {
            "run_id": str(run_id),
            "ingested": len(items),
            "known": known,
            "novel": novel,
            "deduplicated": False,
        }

    def ingest_ci_run(
        self,
        *,
        user_id: str,
        org_id: str,
        project: str,
        source: str,
        commit_sha: Optional[str] = None,
        run_uid: Optional[str] = None,
        items: List[IngestItem],
        results: List[Dict[str, Any]],
        snapshots: List[Dict[str, Any]],
        manifest: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ingesta atómica de un run de CI: run + failures + familias + test_results +
        dom_snapshots en UNA transacción. Idempotente por (org_id, run_uid): si run_uid
        viene y ya existe, no-op devolviendo el run existente con deduplicated=True.

        Lanza PermissionError si no es miembro; ValueError ante status/kind inválido.
        """
        known = 0
        novel = 0
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")

                run_id, existing_summary = self._insert_run_or_get_existing(
                    cur, org_id=org_id, project=project, source=source,
                    commit_sha=commit_sha, run_uid=run_uid,
                )
                if existing_summary is not None:
                    # entrega duplicada concurrente o reintento → devolver el run existente
                    return {
                        "run_id": str(run_id),
                        "ingested": existing_summary.get("ingested", 0),
                        "known": existing_summary.get("known", 0),
                        "novel": existing_summary.get("novel", 0),
                        "results_recorded": existing_summary.get("results_recorded", 0),
                        "snapshots_saved": existing_summary.get("snapshots_saved", 0),
                        "deduplicated": True,
                    }

                for item in items:
                    if self._match_and_insert_failure(cur, org_id=org_id, run_id=run_id, item=item):
                        novel += 1
                    else:
                        known += 1

                for r in results:
                    if "test_name" not in r or "status" not in r:
                        raise ValueError("each result requires 'test_name' and 'status'")
                    if r["status"] not in _CI_STATUSES:
                        raise ValueError(f"invalid status: {r['status']!r}")
                    cur.execute(
                        "insert into public.test_results"
                        " (run_id, org_id, test_name, status, retried)"
                        " values (%s, %s, %s, %s, %s)",
                        (run_id, org_id, r["test_name"], r["status"], r.get("retried", False)),
                    )

                for s in snapshots:
                    if "test_name" not in s or "kind" not in s or "content" not in s:
                        raise ValueError("each snapshot requires 'test_name', 'kind' and 'content'")
                    if s["kind"] not in _CI_KINDS:
                        raise ValueError(f"invalid kind: {s['kind']!r}")
                    cur.execute(
                        "insert into public.dom_snapshots"
                        " (org_id, project, test_name, kind, content, commit_sha)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (org_id, project, s["test_name"], s["kind"], s["content"],
                         s.get("commit_sha")),
                    )

                summary = {
                    "ingested": len(items), "known": known, "novel": novel,
                    "results_recorded": len(results), "snapshots_saved": len(snapshots),
                }
                if manifest is not None:
                    summary["manifest"] = manifest
                cur.execute(
                    "update public.test_runs set summary = %s where id = %s",
                    (Json(summary), run_id),
                )
            conn.commit()
        return {
            "run_id": str(run_id),
            "ingested": len(items),
            "known": known,
            "novel": novel,
            "results_recorded": len(results),
            "snapshots_saved": len(snapshots),
            "deduplicated": False,
        }

    def existing_external_refs(self, *, user_id: str, org_id: str) -> List[str]:
        """Return the external_ref values already present for the org's failures."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select distinct external_ref from public.failures"
                    " where org_id = %s and external_ref is not null"
                    " and exists (select 1 from public.memberships m"
                    "             where m.org_id = %s and m.user_id = %s)",
                    (org_id, org_id, user_id),
                )
                return [r["external_ref"] for r in cur.fetchall()]

    def list_defects(self, *, user_id: str, org_id: str) -> List[Dict[str, Any]]:
        """Return all defect families for the org, filtered to members only."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        f.id,
                        f.title,
                        f.status,
                        f.occurrence_count,
                        f.first_seen,
                        f.last_seen,
                        f.label,
                        exists(
                            select 1 from public.qa_knowledge k
                            where k.org_id = f.org_id
                              and k.defect_family_id = f.id
                              and k.status = 'activo'
                        ) as has_lesson,
                        coalesce(
                            array_agg(distinct r.project)
                            filter (where r.project is not null),
                            '{}'
                        ) as projects
                    from public.defect_families f
                    left join public.failures fl on fl.defect_family_id = f.id
                    left join public.test_runs r on r.id = fl.run_id
                    where f.scope = 'org'
                      and f.org_id = %s
                      and exists (
                          select 1 from public.memberships m
                          where m.org_id = f.org_id and m.user_id = %s
                      )
                    group by f.id
                    order by f.occurrence_count desc, f.last_seen desc
                    """,
                    (org_id, user_id),
                )
                return [
                    {
                        "id": str(r["id"]),
                        "title": r["title"],
                        "status": r["status"],
                        "occurrence_count": r["occurrence_count"],
                        "first_seen": str(r["first_seen"]) if r["first_seen"] is not None else None,
                        "last_seen": str(r["last_seen"]) if r["last_seen"] is not None else None,
                        "label": r["label"],
                        "has_lesson": bool(r["has_lesson"]),
                        "projects": list(r["projects"]),
                    }
                    for r in cur.fetchall()
                ]

    def get_lineage(self, *, user_id: str, defect_id: str) -> Dict[str, Any]:
        """Return a defect family and all its associated failures.

        Returns ``{"family": None, "failures": []}`` when the defect does not
        exist or the user is not a member of the owning org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select f.id, f.title, f.status, f.occurrence_count, f.root_cause
                    from public.defect_families f
                    where f.id = %s
                      and (
                          f.scope = 'global'
                          or exists (
                              select 1 from public.memberships m
                              where m.org_id = f.org_id and m.user_id = %s
                          )
                      )
                    """,
                    (defect_id, user_id),
                )
                fam = cur.fetchone()
                if fam is None:
                    return {"family": None, "failures": []}

                cur.execute(
                    """
                    select fl.id, fl.test_name, fl.error_type, fl.created_at,
                           r.project, r.source
                    from public.failures fl
                    join public.test_runs r on r.id = fl.run_id
                    where fl.defect_family_id = %s
                    order by fl.created_at
                    """,
                    (defect_id,),
                )
                failures = [
                    {
                        "id": str(r["id"]),
                        "test_name": r["test_name"],
                        "error_type": r["error_type"],
                        "project": r["project"],
                        "source": r["source"],
                        "created_at": str(r["created_at"]),
                    }
                    for r in cur.fetchall()
                ]

            return {
                "family": {
                    "id": str(fam["id"]),
                    "title": fam["title"],
                    "status": fam["status"],
                    "occurrence_count": fam["occurrence_count"],
                    "root_cause": fam["root_cause"],
                },
                "failures": failures,
            }

    def get_family_with_failures(self, *, user_id: str, defect_id: str):
        """Familia (con root_cause) + sus fallos recientes (con message/trace) para análisis.

        Devuelve None si la familia no existe o el usuario no es miembro del org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select f.id, f.org_id, f.title, f.status, f.occurrence_count, f.root_cause
                    from public.defect_families f
                    where f.id = %s
                      and (f.scope = 'global' or exists (
                          select 1 from public.memberships m
                          where m.org_id = f.org_id and m.user_id = %s))
                    """,
                    (defect_id, user_id),
                )
                fam = cur.fetchone()
                if fam is None:
                    return None
                cur.execute(
                    """
                    select fl.test_name, fl.error_type, fl.message, fl.trace, r.project
                    from public.failures fl
                    join public.test_runs r on r.id = fl.run_id
                    where fl.defect_family_id = %s
                    order by fl.created_at desc
                    limit 20
                    """,
                    (defect_id,),
                )
                failures = [
                    {"test_name": r["test_name"], "error_type": r["error_type"],
                     "message": r["message"], "trace": r["trace"], "project": r["project"]}
                    for r in cur.fetchall()
                ]
            return {
                "family": {
                    "id": str(fam["id"]), "title": fam["title"], "status": fam["status"],
                    "occurrence_count": fam["occurrence_count"], "root_cause": fam["root_cause"],
                    # org_id para el hook causa-raíz→propuesta (None en familias globales)
                    "org_id": str(fam["org_id"]) if fam["org_id"] else None,
                },
                "failures": failures,
            }

    def save_root_cause(self, *, user_id: str, defect_id: str, text: str) -> bool:
        """Persiste el análisis de causa raíz. Devuelve False si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update public.defect_families
                    set root_cause = %s
                    where id = %s
                      and (scope = 'global' or exists (
                          select 1 from public.memberships m
                          where m.org_id = public.defect_families.org_id and m.user_id = %s))
                    """,
                    (text, defect_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def get_run_assurance_data(self, *, user_id: str, run_id: str) -> Dict[str, Any]:
        """Return a test run's assurance data including its defect families.

        Returns ``{"run": None, "summary": {}, "families": []}`` when the run
        does not exist or the user is not a member of the owning org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select r.id, r.project, r.source, r.summary
                    from public.test_runs r
                    where r.id = %s
                      and exists (select 1 from public.memberships m where m.org_id = r.org_id and m.user_id = %s)
                    """,
                    (run_id, user_id),
                )
                run = cur.fetchone()
                if run is None:
                    return {"run": None, "summary": {}, "families": []}
                cur.execute(
                    """
                    select df.id, df.title, df.occurrence_count, count(fl.id) as run_count
                    from public.failures fl
                    join public.defect_families df on df.id = fl.defect_family_id
                    where fl.run_id = %s
                    group by df.id
                    order by df.occurrence_count desc
                    """,
                    (run_id,),
                )
                families = [
                    {"id": str(r["id"]), "title": r["title"],
                     "occurrence_count": r["occurrence_count"], "run_count": r["run_count"]}
                    for r in cur.fetchall()
                ]
            return {
                "run": {"id": str(run["id"]), "project": run["project"], "source": run["source"]},
                "summary": run["summary"] or {},
                "families": families,
            }

    def record_test_results(
        self, *, user_id: str, org_id: str, run_id: str, results: List[Dict[str, Any]]
    ) -> int:
        """Persiste el resultado por test de un run (incluye pass). Devuelve el nº insertado.

        Lanza PermissionError si el usuario no es miembro del org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute(
                    "select 1 from public.test_runs where id = %s and org_id = %s",
                    (run_id, org_id),
                )
                if cur.fetchone() is None:
                    raise ValueError("run does not belong to the organization")
                for r in results:
                    if "test_name" not in r or "status" not in r:
                        raise ValueError("each result requires 'test_name' and 'status'")
                    if r["status"] not in ("pass", "fail", "flaky", "skipped"):
                        raise ValueError(f"invalid status: {r['status']!r}")
                    cur.execute(
                        "insert into public.test_results"
                        " (run_id, org_id, test_name, status, retried)"
                        " values (%s, %s, %s, %s, %s)",
                        (run_id, org_id, r["test_name"], r["status"], r.get("retried", False)),
                    )
            conn.commit()
        return len(results)

    def save_dom_snapshots(
        self, *, user_id: str, org_id: str, project: str, snapshots: List[Dict[str, Any]]
    ) -> int:
        """Persiste snapshots DOM (kind last_green|failure). Devuelve el nº insertado.

        Lanza PermissionError si el usuario no es miembro del org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                for s in snapshots:
                    if "test_name" not in s or "kind" not in s or "content" not in s:
                        raise ValueError("each snapshot requires 'test_name', 'kind' and 'content'")
                    if s["kind"] not in ("last_green", "failure"):
                        raise ValueError(f"invalid kind: {s['kind']!r}")
                    cur.execute(
                        "insert into public.dom_snapshots"
                        " (org_id, project, test_name, kind, content, commit_sha)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (org_id, project, s["test_name"], s["kind"], s["content"],
                         s.get("commit_sha")),
                    )
            conn.commit()
        return len(snapshots)

    def get_triage_inputs(self, *, user_id: str, run_id: str) -> Dict[str, Any]:
        """Recupera, por cada fallo de un run, los hechos para el triaje (is_novel,
        family_label, retry_passed_in_run, intermittent_same_sha, has_green_baseline,
        dom_changed) + el contexto del run. mass_cofailure NO se calcula aquí (depende
        de classify_error → lo hace el servicio en F2e). None si no es miembro/no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select r.id, r.org_id, r.project, r.commit_sha from public.test_runs r"
                    " where r.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (run_id, user_id),
                )
                run = cur.fetchone()
                if run is None:
                    return {"run": None, "failures": []}
                org_id, project, commit_sha = run["org_id"], run["project"], run["commit_sha"]

                cur.execute(
                    "select f.id as failure_id, f.test_name, f.error_type, f.message, f.trace,"
                    "       f.fingerprint, f.defect_family_id, df.label as family_label"
                    " from public.failures f"
                    " left join public.defect_families df on df.id = f.defect_family_id"
                    " where f.run_id = %s",
                    (run_id,),
                )
                failures = cur.fetchall()
                family_ids = [f["defect_family_id"] for f in failures if f["defect_family_id"]]

                recurrent: set = set()
                lineage: Dict[Any, list] = {}
                if family_ids:
                    cur.execute(
                        "select distinct defect_family_id from public.failures"
                        " where defect_family_id = any(%s) and org_id = %s and run_id <> %s",
                        (family_ids, org_id, run_id),
                    )
                    recurrent = {r["defect_family_id"] for r in cur.fetchall()}
                    cur.execute(
                        "select fl.defect_family_id as fid,"
                        "       array_agg(distinct r2.project) as projects"
                        " from public.failures fl join public.test_runs r2 on r2.id = fl.run_id"
                        " where fl.defect_family_id = any(%s) and fl.org_id = %s"
                        " group by fl.defect_family_id",
                        (family_ids, org_id),
                    )
                    lineage = {r["fid"]: list(r["projects"]) for r in cur.fetchall()}

                cur.execute(
                    "select distinct test_name from public.test_results"
                    " where run_id = %s and (status = 'flaky' or (status = 'pass' and retried))",
                    (run_id,),
                )
                retry_passed = {r["test_name"] for r in cur.fetchall()}

                intermittent: set = set()
                if commit_sha:
                    cur.execute(
                        "select tr.test_name from public.test_results tr"
                        " join public.test_runs r2 on r2.id = tr.run_id"
                        " where r2.org_id = %s and r2.project = %s and r2.commit_sha = %s"
                        " group by tr.test_name"
                        " having bool_or(tr.status = 'pass')"
                        "    and bool_or(tr.status in ('fail', 'flaky'))",
                        (org_id, project, commit_sha),
                    )
                    intermittent = {r["test_name"] for r in cur.fetchall()}

                cur.execute(
                    "select distinct on (test_name) test_name, content from public.dom_snapshots"
                    " where org_id = %s and project = %s and kind = 'last_green'"
                    " order by test_name, created_at desc",
                    (org_id, project),
                )
                green = {r["test_name"]: r["content"] for r in cur.fetchall()}
                cur.execute(
                    "select distinct on (test_name) test_name, content from public.dom_snapshots"
                    " where org_id = %s and project = %s and kind = 'failure'"
                    "   and commit_sha is not distinct from %s"
                    " order by test_name, created_at desc",
                    (org_id, project, commit_sha),
                )
                fail_dom = {r["test_name"]: r["content"] for r in cur.fetchall()}

            out = []
            for f in failures:
                fam = f["defect_family_id"]
                tn = f["test_name"]
                out.append({
                    "failure_id": str(f["failure_id"]),
                    "fingerprint": f["fingerprint"],
                    "family_id": str(fam) if fam else None,
                    "lineage_projects": lineage.get(fam, []),
                    "error_type": f["error_type"],
                    "message": f["message"],
                    "trace": f["trace"],
                    "is_novel": (fam not in recurrent) if fam else True,
                    "family_label": f["family_label"] or "unknown",
                    "retry_passed_in_run": tn in retry_passed,
                    "intermittent_same_sha": tn in intermittent,
                    "has_green_baseline": tn in green,
                    "dom_changed": dom_changed(fail_dom.get(tn), green.get(tn)),
                })
        return {
            "run": {"id": str(run["id"]), "org_id": str(org_id),
                    "project": project, "commit_sha": commit_sha},
            "failures": out,
        }

    def save_triage_verdicts(
        self, *, user_id: str, org_id: str, run_id: str, verdicts: List[Dict[str, Any]]
    ) -> int:
        """Reemplaza (delete+insert) los veredictos del run → idempotente. Lanza
        PermissionError si el usuario no es miembro del org."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute(
                    "select 1 from public.test_runs where id = %s and org_id = %s",
                    (run_id, org_id),
                )
                if cur.fetchone() is None:
                    raise ValueError("run does not belong to the organization")
                cur.execute(
                    "delete from public.triage_verdicts where run_id = %s and org_id = %s",
                    (run_id, org_id),
                )
                for v in verdicts:
                    cur.execute(
                        "insert into public.triage_verdicts"
                        " (failure_id, run_id, org_id, category, confidence, rule_applied,"
                        "  evidence_bundle, requires_approval, llm_assisted, status)"
                        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (v["failure_id"], run_id, org_id, v["category"], v["confidence"],
                         v["rule_applied"], Json(v.get("evidence_bundle")),
                         v["requires_approval"], v["llm_assisted"], v.get("status", "resolved")),
                    )
            conn.commit()
        return len(verdicts)

    def get_triage_for_run(self, *, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        """Veredictos persistidos de un run (vacío si no es miembro / no existe)."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select tv.id, tv.failure_id, tv.category, tv.confidence, tv.rule_applied,"
                    "       tv.evidence_bundle, tv.requires_approval, tv.llm_assisted, tv.status"
                    " from public.triage_verdicts tv"
                    " join public.test_runs r on r.id = tv.run_id"
                    " where tv.run_id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)"
                    # orden TOTAL: created_at empata en el insert transaccional; failure_id
                    # (único por fallo) rompe el empate → evidencia byte-reproducible.
                    " order by tv.created_at, tv.failure_id",
                    (run_id, user_id),
                )
                return [
                    {
                        "id": str(r["id"]), "failure_id": str(r["failure_id"]),
                        "category": r["category"], "confidence": r["confidence"],
                        "rule_applied": r["rule_applied"], "evidence_bundle": r["evidence_bundle"],
                        "requires_approval": r["requires_approval"],
                        "llm_assisted": r["llm_assisted"], "status": r["status"],
                    }
                    for r in cur.fetchall()
                ]

    def count_failures_for_run(self, *, user_id: str, run_id: str) -> int:
        """Nº de fallos ingeridos de un run (0 si no es miembro / no existe).

        Distingue un run genuinamente VERDE (0 fallos → certificable como apto) de
        uno con fallos aún SIN TRIAR (fallos > 0 pero sin veredictos → no certificar).
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) as n from public.failures fl"
                    " join public.test_runs r on r.id = fl.run_id"
                    " where fl.run_id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (run_id, user_id),
                )
                return int(cur.fetchone()["n"])

    def update_triage_verdict(
        self, *, user_id: str, verdict_id: str, category: str, confidence: float,
        requires_approval: bool, llm_assisted: bool, status: str,
        evidence_bundle: Any,
    ) -> bool:
        """Actualiza un veredicto (resolución de tiebreak). Membership-gated vía el
        org del veredicto. Devuelve False si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.triage_verdicts tv set category = %s, confidence = %s,"
                    "  requires_approval = %s, llm_assisted = %s, status = %s, evidence_bundle = %s"
                    " where tv.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = tv.org_id and m.user_id = %s)",
                    (category, confidence, requires_approval, llm_assisted, status,
                     Json(evidence_bundle), verdict_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def set_family_label(self, *, user_id: str, family_id: str, label: str,
                         reason: Optional[str] = None) -> bool:
        """Etiqueta una familia (lazo de aprendizaje) y registra la corrección
        (motor vs humano) en triage_corrections. Devuelve False si no es miembro /
        no existe. Lanza ValueError si el label no es válido."""
        if label not in ("flaky", "real", "maintenance", "infra", "unknown"):
            raise ValueError(f"invalid label: {label!r}")
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.defect_families set label = %s"
                    " where id = %s and (scope = 'global' or exists (select 1 from public.memberships m"
                    "   where m.org_id = public.defect_families.org_id and m.user_id = %s))"
                    " returning org_id",
                    (label, family_id, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    return False
                org_id = row["org_id"]
                if org_id is not None:
                    cur.execute(
                        "select tv.category, tv.llm_assisted from public.triage_verdicts tv"
                        " join public.failures f on f.id = tv.failure_id"
                        " where f.defect_family_id = %s order by tv.created_at desc limit 1",
                        (family_id,),
                    )
                    er = cur.fetchone()
                    engine_category = (
                        ("unknown" if er["llm_assisted"] else er["category"]) if er else None
                    )
                    cur.execute(
                        "insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, source, reason, corrected_by)"
                        " values (%s, %s, %s, %s, 'family_label', %s, %s)",
                        (org_id, family_id, engine_category, label, reason, user_id),
                    )
            conn.commit()
        return True

    def list_runs(self, *, user_id: str, org_id: str, project: Optional[str] = None,
                  limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Histórico de runs navegable (por proyecto y fecha), con el veredicto del
        acta más reciente y el nº de fallos. [] si el usuario no es miembro."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return []
                q = (
                    "select r.id, r.project, r.source, r.commit_sha, r.created_at,"
                    " c.verdict, c.risk_score,"
                    " (select count(*) from public.failures f where f.run_id = r.id) as failures"
                    " from public.test_runs r"
                    " left join lateral ("
                    "   select verdict, risk_score from public.certificates c"
                    "   where c.run_id = r.id order by c.created_at desc limit 1"
                    " ) c on true"
                    " where r.org_id = %s"
                )
                params: List[Any] = [org_id]
                if project:
                    q += " and r.project = %s"
                    params.append(project)
                q += " order by r.created_at desc limit %s offset %s"
                params.extend([min(max(limit, 1), 100), max(offset, 0)])
                cur.execute(q, tuple(params))
                return [
                    {"id": str(r["id"]), "project": r["project"], "source": r["source"],
                     "commit_sha": r["commit_sha"],
                     "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                     "verdict": r["verdict"], "risk_score": r["risk_score"],
                     "failures": r["failures"]}
                    for r in cur.fetchall()
                ]

    def get_calibration_metrics(self, *, user_id: str, org_id: str) -> Optional[Dict[str, Any]]:
        """Métrica del foso por org. None si el usuario no es miembro."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return None
                cur.execute(
                    "select count(*) as total,"
                    " count(*) filter (where engine_category = human_category) as aciertos"
                    " from public.triage_corrections where org_id = %s", (org_id,))
                agg = cur.fetchone()
                total, aciertos = agg["total"], agg["aciertos"]
                cur.execute("select count(*) as n from public.defect_families"
                            " where org_id = %s and label is not null and label <> 'unknown'", (org_id,))
                familias_calibradas = cur.fetchone()["n"]
                cur.execute("select human_category, count(*) as n from public.triage_corrections"
                            " where org_id = %s group by human_category", (org_id,))
                por_categoria = {r["human_category"]: r["n"] for r in cur.fetchall()}
        return {"total": total, "aciertos": aciertos,
                "accuracy": (aciertos / total) if total else 0.0,
                "familias_calibradas": familias_calibradas, "por_categoria": por_categoria}

    def get_run_actionable_verdicts(self, *, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        """Veredictos 'resolved' del run + datos del fallo (test_name, error_type, familia).
        Vacío si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select tv.id as verdict_id, tv.failure_id, tv.org_id, tv.category,"
                    "       tv.confidence, tv.requires_approval, tv.evidence_bundle,"
                    "       f.test_name, f.error_type, f.defect_family_id"
                    " from public.triage_verdicts tv"
                    " join public.test_runs r on r.id = tv.run_id"
                    " join public.failures f on f.id = tv.failure_id"
                    " where tv.run_id = %s and tv.status = 'resolved'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = r.org_id and m.user_id = %s)"
                    " order by tv.created_at",
                    (run_id, user_id),
                )
                return [
                    {"verdict_id": str(r["verdict_id"]), "failure_id": str(r["failure_id"]),
                     "org_id": str(r["org_id"]), "category": r["category"],
                     "confidence": r["confidence"], "requires_approval": r["requires_approval"],
                     "evidence_bundle": r["evidence_bundle"], "test_name": r["test_name"],
                     "error_type": r["error_type"],
                     "defect_family_id": str(r["defect_family_id"]) if r["defect_family_id"] else None}
                    for r in cur.fetchall()
                ]

    def search_families_semantic(self, *, user_id: str, org_id: str,
                                 query_embedding: Sequence[float], k: int = 8) -> List[Dict[str, Any]]:
        """Familias del tenant más similares a la consulta (coseno sobre el centroide).
        Membership-gated; solo familias con centroide. [] si no es miembro."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return []
                cur.execute(
                    "select id, signature, label, root_cause, occurrence_count, title"
                    " from public.defect_families"
                    " where scope = 'org' and org_id = %s and centroid is not null"
                    " order by centroid <=> %s limit %s",
                    (org_id, Vector(list(query_embedding)), k),
                )
                return [
                    {"family_id": str(r["id"]), "signature": r["signature"], "label": r["label"],
                     "root_cause": r["root_cause"], "occurrence_count": r["occurrence_count"],
                     "title": r["title"]}
                    for r in cur.fetchall()
                ]

    def get_selfheal_context(self, *, user_id: str, failure_id: str) -> Optional[Dict[str, Any]]:
        """Contexto para el self-heal de un fallo: el error + los DOM verde/rojo del test.
        None si no es miembro / no existe el fallo."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select f.message, f.trace, f.test_name, f.file, r.org_id, r.project, r.commit_sha"
                    " from public.failures f join public.test_runs r on r.id = f.run_id"
                    " where f.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (failure_id, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    "select content from public.dom_snapshots"
                    " where org_id = %s and project = %s and test_name = %s and kind = 'last_green'"
                    " order by created_at desc limit 1",
                    (row["org_id"], row["project"], row["test_name"]),
                )
                green = cur.fetchone()
                cur.execute(
                    "select content from public.dom_snapshots"
                    " where org_id = %s and project = %s and test_name = %s and kind = 'failure'"
                    "   and commit_sha is not distinct from %s order by created_at desc limit 1",
                    (row["org_id"], row["project"], row["test_name"], row["commit_sha"]),
                )
                fail = cur.fetchone()
        return {
            "error_message": row["message"], "trace": row["trace"],
            "green_dom": green["content"] if green else None,
            "failure_dom": fail["content"] if fail else None,
            "file": row["file"],
        }
