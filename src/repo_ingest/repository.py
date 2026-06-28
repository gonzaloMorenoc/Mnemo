from typing import Dict, List, Sequence

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.config import DATABASE_URL
from src.defects.embedder import LocalEmbedder


class TestAssetRepository:
    def __init__(self, db_url: str = DATABASE_URL, embedder=None):
        self.db_url = db_url
        self.embedder = embedder or LocalEmbedder()

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self.db_url, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id=%s and user_id=%s) as ok",
            (org_id, user_id),
        )
        return bool(cur.fetchone()["ok"])

    def replace_for_repo(
        self,
        *,
        user_id: str,
        org_id: str,
        repo: str,
        assets: List[Dict],
    ) -> int:
        """Delete all assets for (org_id, repo) then insert the new ones.

        Returns the number of rows inserted, or 0 for non-members.
        Each asset dict must have keys: path, content; optionally framework, domain.
        """
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return 0
            cur.execute(
                "delete from public.test_assets"
                " where org_id=%s and repo_full_name=%s",
                (org_id, repo),
            )
            count = 0
            for asset in assets:
                content = (asset.get("content") or "")[:8000]
                emb = Vector(list(self.embedder.embed(content)))
                cur.execute(
                    "insert into public.test_assets"
                    " (org_id, repo_full_name, path, framework, domain, content, embedding)"
                    " values (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        org_id,
                        repo,
                        asset.get("path"),
                        asset.get("framework"),
                        asset.get("domain"),
                        content,
                        emb,
                    ),
                )
                count += 1
            conn.commit()
            return count

    def list_assets(self, *, user_id: str, org_id: str) -> List[Dict]:
        """Return path, framework, domain for all assets in the org."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            cur.execute(
                "select id, repo_full_name, path, framework, domain, created_at"
                " from public.test_assets where org_id=%s"
                " order by created_at desc limit 500",
                (org_id,),
            )
            return [dict(r) for r in cur.fetchall()]

    def search_semantic(
        self,
        *,
        user_id: str,
        org_id: str,
        query_embedding: Sequence[float],
        k: int = 5,
    ) -> List[Dict]:
        """Return the k nearest test assets by cosine distance."""
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return []
            cur.execute(
                "select id, repo_full_name, path, framework, domain, content"
                " from public.test_assets"
                " where org_id=%s and embedding is not null"
                " order by embedding <=> %s limit %s",
                (org_id, Vector(list(query_embedding)), k),
            )
            return [dict(r) for r in cur.fetchall()]
