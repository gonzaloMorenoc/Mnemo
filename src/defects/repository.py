from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.config import DATABASE_URL
from src.defects.centroid import update_centroid
from src.defects.match import FamilyCandidate, decide_match
from src.ingest.models import FailureRecord


@dataclass
class IngestItem:
    rec: FailureRecord
    fingerprint: str
    embedding: Sequence[float]


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
        conn = psycopg.connect(self.db_url, row_factory=dict_row)
        register_vector(conn)
        return conn

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
        embedding: Sequence[float],
        limit: int = 10,
    ) -> List[FamilyCandidate]:
        cur.execute(
            """
            select id, signature, centroid
            from public.defect_families
            where scope = 'org' and org_id = %s and centroid is not null
            order by centroid <=> %s
            limit %s
            """,
            (org_id, Vector(list(embedding)), limit),
        )
        rows = cur.fetchall()
        return [
            FamilyCandidate(
                family_id=str(r["id"]),
                signature=r["signature"],
                centroid=list(r["centroid"]),
            )
            for r in rows
        ]

    def ingest_run(
        self,
        *,
        user_id: str,
        org_id: str,
        project: str,
        source: str,
        items: List[IngestItem],
    ) -> Dict[str, Any]:
        """Ingest a test run and classify each failure into a defect family.

        Returns a dict with keys: run_id, ingested, known, novel.
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

                cur.execute(
                    "insert into public.test_runs (org_id, project, source)"
                    " values (%s, %s, %s) returning id",
                    (org_id, project, source),
                )
                run_id = cur.fetchone()["id"]

                for item in items:
                    cands = self._query_candidates(
                        cur, org_id=org_id, embedding=item.embedding
                    )
                    decision = decide_match(
                        fingerprint=item.fingerprint,
                        embedding=item.embedding,
                        candidates=cands,
                    )

                    if decision.is_new:
                        novel += 1
                        title = (
                            item.rec.error_type
                            or item.rec.message[:80]
                            or "unknown"
                        )
                        cur.execute(
                            """
                            insert into public.defect_families
                                (scope, org_id, signature, title, occurrence_count, centroid)
                            values ('org', %s, %s, %s, 1, %s)
                            returning id
                            """,
                            (
                                org_id,
                                item.fingerprint,
                                title,
                                Vector(list(item.embedding)),
                            ),
                        )
                        family_id = cur.fetchone()["id"]
                    else:
                        known += 1
                        family_id = decision.family_id
                        cur.execute(
                            "select occurrence_count, centroid"
                            " from public.defect_families where id = %s for update",
                            (family_id,),
                        )
                        fam = cur.fetchone()
                        new_centroid = update_centroid(
                            list(fam["centroid"]) if fam["centroid"] is not None else None,
                            fam["occurrence_count"],
                            list(item.embedding),
                        )
                        cur.execute(
                            """
                            update public.defect_families
                            set occurrence_count = occurrence_count + 1,
                                last_seen = now(),
                                centroid = %s
                            where id = %s
                            """,
                            (Vector(new_centroid), family_id),
                        )

                    cur.execute(
                        """
                        insert into public.failures
                            (run_id, org_id, test_name, error_type, message, trace,
                             fingerprint, embedding, sanitized, defect_family_id)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s)
                        """,
                        (
                            run_id,
                            org_id,
                            item.rec.test_name,
                            item.rec.error_type,
                            item.rec.message,
                            item.rec.trace,
                            item.fingerprint,
                            Vector(list(item.embedding)),
                            family_id,
                        ),
                    )

                summary = {"ingested": len(items), "known": known, "novel": novel}
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
        }

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
                    select f.id, f.title, f.status, f.occurrence_count
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
                },
                "failures": failures,
            }

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
