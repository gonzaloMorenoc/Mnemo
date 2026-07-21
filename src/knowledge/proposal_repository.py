"""Acceso a datos de las propuestas de conocimiento (public.knowledge_proposals).

El pooler hace BYPASS de RLS → cada método valida membership en la capa de app
(la RLS de la tabla es solo defensa en profundidad). La aprobación es atómica:
CAS del estado + INSERT en qa_knowledge en la MISMA transacción.
"""
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from pgvector import Vector

from src.config import DATABASE_URL
from src.db.pool import get_pool
from src.defects.embedder import LocalEmbedder
from src.knowledge.repository import embedding_text, insert_qa_knowledge

# Familias que necesitan una propuesta nueva: sin lección en memoria Y sin ninguna
# propuesta previa (ni pendiente, ni aprobada, ni rechazada → no resucita lo descartado).
# El run_id sale del fallo más reciente de la familia (trazabilidad honesta).
_CANDIDATE_WHERE = """
    from public.defect_families f
    where f.org_id = %(org)s
      and not exists (select 1 from public.qa_knowledge k
                      where k.org_id = %(org)s and k.defect_family_id = f.id)
      and not exists (select 1 from public.knowledge_proposals p
                      where p.defect_family_id = f.id)
"""

_PROPOSAL_COLS = ("id, org_id, defect_family_id, run_id, kind, title, challenge, approach,"
                  " domain, outcome, tags, status, created_at")


class KnowledgeProposalRepository:
    def __init__(self, db_url: str = DATABASE_URL, embedder=None):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url
        self.embedder = embedder or LocalEmbedder()

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        return bool(cur.fetchone()["ok"])

    def _rows(self, cur) -> List[Dict[str, Any]]:
        return [
            {"id": str(r["id"]), "org_id": str(r["org_id"]),
             "defect_family_id": str(r["defect_family_id"]),
             "run_id": str(r["run_id"]) if r["run_id"] else None,
             "kind": r["kind"], "title": r["title"], "challenge": r["challenge"],
             "approach": r["approach"], "domain": r["domain"], "outcome": r["outcome"],
             "tags": r["tags"], "status": r["status"],
             "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in cur.fetchall()
        ]

    def candidate_families(self, *, user_id: str, org_id: str, limit: int = 5,
                           family_ids: Optional[Sequence[str]] = None) -> List[Dict[str, Any]]:
        """Familias sin lección ni propuesta previa (org-scoped + membership).

        Si se pasa `family_ids`, se intersecta con las candidatas de ESTA org (una
        familia de otra org no aparece → anti confused-deputy). [] si no es miembro."""
        params: Dict[str, Any] = {"org": org_id, "limit": limit}
        where = _CANDIDATE_WHERE
        if family_ids is not None:
            where += " and f.id = any(%(ids)s::uuid[])"
            params["ids"] = list(family_ids)
        sql = ("select f.id, f.title, f.occurrence_count,"
               " (select fa.run_id from public.failures fa where fa.defect_family_id = f.id"
               "  order by fa.created_at desc limit 1) as run_id"
               f" {where} order by f.occurrence_count desc nulls last limit %(limit)s")
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            cur.execute(sql, params)
            return [{"id": str(r["id"]), "title": r["title"],
                     "occurrence_count": r["occurrence_count"],
                     "run_id": str(r["run_id"]) if r["run_id"] else None}
                    for r in cur.fetchall()]

    def count_candidate_families(self, *, user_id: str, org_id: str) -> int:
        """Cuántas familias siguen sin lección ni propuesta (para `remaining`)."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return 0
            cur.execute(f"select count(*) as n {_CANDIDATE_WHERE}", {"org": org_id})
            return int(cur.fetchone()["n"])

    def list_proposals(self, *, user_id: str, org_id: str,
                       status: str = "pending") -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            cur.execute(f"select {_PROPOSAL_COLS} from public.knowledge_proposals"
                        " where org_id=%s and status=%s order by created_at desc",
                        (org_id, status))
            return self._rows(cur)

    def upsert_proposal(self, *, user_id: str, org_id: str, defect_family_id: str,
                        run_id: Optional[str], created_by: str, kind: str, title: str,
                        challenge: Optional[str], approach: Optional[str],
                        domain: Optional[str], outcome: Optional[str],
                        tags: Sequence[str]) -> Optional[Dict[str, Any]]:
        """Crea/refresca una propuesta pendiente para la familia. `ON CONFLICT ... WHERE
        status='pending'`: si ya está aprobada/rechazada NO se toca (no resucita). None si
        no es miembro o si el conflicto no era pendiente (no-op)."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            cur.execute(
                "insert into public.knowledge_proposals"
                " (org_id, defect_family_id, run_id, kind, title, challenge, approach,"
                "  domain, outcome, tags, created_by)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " on conflict (defect_family_id) do update set"
                "  run_id=excluded.run_id, kind=excluded.kind, title=excluded.title,"
                "  challenge=excluded.challenge, approach=excluded.approach,"
                "  domain=excluded.domain, outcome=excluded.outcome, tags=excluded.tags"
                " where knowledge_proposals.status='pending'"
                f" returning {_PROPOSAL_COLS}",
                (org_id, defect_family_id, run_id, kind, title, challenge, approach,
                 domain, outcome, list(tags or []), created_by),
            )
            rows = self._rows(cur)
            conn.commit()
            return rows[0] if rows else None

    def approve(self, *, user_id: str, proposal_id: str, kind: str, title: str,
                challenge: Optional[str], approach: Optional[str], domain: Optional[str],
                outcome: Optional[str], tags: Sequence[str]) -> Optional[Dict[str, Any]]:
        """Aprueba de forma ATÓMICA: CAS del estado (pending→approved, exige owner/admin) +
        INSERT en qa_knowledge en la MISMA conexión. El embedding se calcula ANTES de la
        transacción (no retener la transacción durante el cómputo del modelo). Doble clic →
        0 filas en el CAS → no-op. None si no es pendiente / no autorizado."""
        emb = Vector(list(self.embedder.embed(embedding_text(title, challenge, approach))))
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update public.knowledge_proposals p set status='approved',"
                "  approved_by=%s, approved_at=now()"
                " where p.id=%s and p.status='pending'"
                "   and exists(select 1 from public.memberships m"
                "     where m.org_id=p.org_id and m.user_id=%s and m.role in ('owner','admin'))"
                " returning p.org_id, p.defect_family_id, p.run_id",
                (user_id, proposal_id, user_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            item = insert_qa_knowledge(
                cur, org_id=str(row["org_id"]), kind=kind, title=title, challenge=challenge,
                approach=approach, outcome=outcome, domain=domain, tags=tags, project=None,
                source="auto_triage", confidence="inferido",
                defect_family_id=str(row["defect_family_id"]),
                run_id=str(row["run_id"]) if row["run_id"] else None,
                created_by=user_id, embedding=emb,
            )
            conn.commit()
            return dict(item)

    def reject(self, *, user_id: str, proposal_id: str, reason: str = "") -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update public.knowledge_proposals p set status='rejected', reject_reason=%s"
                " where p.id=%s and p.status='pending'"
                "   and exists(select 1 from public.memberships m"
                "     where m.org_id=p.org_id and m.user_id=%s and m.role in ('owner','admin'))",
                (reason, proposal_id, user_id),
            )
            ok = cur.rowcount > 0
            conn.commit()
        return ok
