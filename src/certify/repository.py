from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.config import DATABASE_URL
from src.db.pool import get_pool


class CertificateRepository:
    """Acceso a datos de certificados (append-only). El pooler bypasea RLS → membership
    en la capa de app en cada método."""

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def _set_claims(self, conn: psycopg.Connection, user_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def get_run_meta(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select r.org_id, r.project, r.commit_sha, r.summary from public.test_runs r"
                    " where r.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (run_id, user_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"org_id": str(row["org_id"]), "project": row["project"],
                "commit_sha": row["commit_sha"],
                "manifest": (row["summary"] or {}).get("manifest")}

    def is_org_admin(self, *, user_id: str, org_id: str) -> bool:
        """True si el usuario es owner/admin de la org (para gatear la emisión a mano)."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id=%s and user_id=%s and role in ('owner','admin')) as ok",
                            (org_id, user_id))
                return bool(cur.fetchone()["ok"])

    def save_certificate(self, *, user_id: str, org_id: str, run_id: str,
                         canonical_json: Dict[str, Any], signature: str, verdict: str,
                         risk_score: int, sign_offs: Any, mnemo_version: str,
                         model_version: str) -> str:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute("select 1 from public.test_runs where id = %s and org_id = %s",
                            (run_id, org_id))
                if cur.fetchone() is None:
                    raise ValueError("run does not belong to the organization")
                cur.execute(
                    "insert into public.certificates"
                    " (run_id, org_id, canonical_json, signature, verdict, risk_score,"
                    "  sign_offs, mnemo_version, model_version)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                    (run_id, org_id, Json(canonical_json), signature, verdict, risk_score,
                     Json(sign_offs), mnemo_version, model_version),
                )
                cid = str(cur.fetchone()["id"])
            conn.commit()
        return cid

    def get_certificate(self, *, user_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select c.id, c.run_id, c.org_id, c.canonical_json, c.signature, c.verdict,"
                    "       c.risk_score, c.sign_offs, c.mnemo_version, c.model_version, c.created_at"
                    " from public.certificates c"
                    " where c.run_id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = c.org_id and m.user_id = %s)"
                    " order by c.created_at desc limit 1",
                    (run_id, user_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"id": str(row["id"]), "run_id": str(row["run_id"]), "org_id": str(row["org_id"]),
                "canonical_json": row["canonical_json"], "signature": row["signature"],
                "verdict": row["verdict"], "risk_score": row["risk_score"],
                "sign_offs": row["sign_offs"], "mnemo_version": row["mnemo_version"],
                "model_version": row["model_version"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None}
