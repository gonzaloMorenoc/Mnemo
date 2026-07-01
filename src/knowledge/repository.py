from typing import Any, Dict, List, Optional, Sequence

import psycopg
from pgvector import Vector
from psycopg.rows import dict_row

from src.config import DATABASE_URL
from src.db.pool import get_pool
from src.defects.embedder import LocalEmbedder

_KINDS = {"regla_negocio", "flujo", "riesgo", "glosario", "leccion", "reto", "patron"}


class QaKnowledgeRepository:
    def __init__(self, db_url: str = DATABASE_URL, embedder=None):
        self.db_url = db_url
        self.embedder = embedder or LocalEmbedder()

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        return bool(cur.fetchone()["ok"])

    def create_item(self, *, user_id: str, org_id: str, kind: str, title: str,
                    challenge: Optional[str] = None, approach: Optional[str] = None,
                    outcome: Optional[str] = None, domain: Optional[str] = None,
                    tags: Optional[Sequence[str]] = None, project: Optional[str] = None,
                    source: str = "manual", confidence: str = "confirmado",
                    defect_family_id: Optional[str] = None, run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if kind not in _KINDS:
            raise ValueError(f"kind inválido: {kind}")
        text = "\n".join(p for p in (title, challenge, approach) if p)
        emb = Vector(list(self.embedder.embed(text)))
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            cur.execute(
                "insert into public.qa_knowledge"
                " (org_id, kind, title, challenge, approach, outcome, domain, tags, project,"
                "  source, confidence, defect_family_id, run_id, created_by, embedding)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " returning id, kind, title, domain, tags, confidence, created_at",
                (org_id, kind, title, challenge, approach, outcome, domain, list(tags or []),
                 project, source, confidence, defect_family_id, run_id, user_id, emb),
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row)

    def list_items(self, *, user_id: str, org_id: str, kind: Optional[str] = None,
                   domain: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            q = ("select id, kind, title, challenge, approach, outcome, domain, tags, project,"
                 " source, confidence, created_at from public.qa_knowledge where org_id=%s")
            params: list = [org_id]
            if kind:
                q += " and kind=%s"; params.append(kind)
            if domain:
                q += " and domain=%s"; params.append(domain)
            q += " order by created_at desc limit 200"
            cur.execute(q, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def get_item(self, *, user_id: str, org_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return None
            cur.execute("select * from public.qa_knowledge where id=%s and org_id=%s", (item_id, org_id))
            row = cur.fetchone()
            return dict(row) if row else None

    def search_semantic(self, *, user_id: str, org_id: str,
                        query_embedding: Sequence[float], k: int = 8) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            cur.execute(
                "select id, kind, title, challenge, approach, outcome, domain, confidence"
                " from public.qa_knowledge"
                " where org_id=%s and embedding is not null"
                " order by embedding <=> %s limit %s",
                (org_id, Vector(list(query_embedding)), k),
            )
            return [dict(r) for r in cur.fetchall()]
