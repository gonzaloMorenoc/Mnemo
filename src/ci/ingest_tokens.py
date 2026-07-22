"""Tokens de ingesta CI por organización (public.ingest_tokens).

Formato del token: `mnemo_it_<48 hex>`. En BD solo vive el sha256; el claro se
devuelve UNA vez al crear. El token actúa con la identidad de su creador
(created_by): los membership-checks del pipeline aplican sin casos especiales,
y revocar el membership del creador desactiva de facto sus tokens.
El pooler hace BYPASS de RLS → cada método valida membership en la capa de app.
"""
import hashlib
import secrets
from typing import Any, Dict, List, Optional

import psycopg

from src.config import DATABASE_URL
from src.db.pool import get_pool

TOKEN_PREFIX = "mnemo_it_"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IngestTokenRepository:
    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def create_token(self, *, user_id: str, org_id: str,
                     name: str) -> Optional[Dict[str, Any]]:
        """Crea un token (owner/admin). Devuelve el token EN CLARO (única vez)."""
        token = TOKEN_PREFIX + secrets.token_hex(24)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select exists(select 1 from public.memberships"
                " where org_id=%s and user_id=%s and role in ('owner','admin')) as ok",
                (org_id, user_id),
            )
            if not cur.fetchone()["ok"]:
                return None
            cur.execute(
                "insert into public.ingest_tokens (org_id, name, token_hash, created_by)"
                " values (%s,%s,%s,%s) returning id, name, created_at",
                (org_id, name, _hash(token), user_id),
            )
            row = cur.fetchone()
            conn.commit()
        return {"id": str(row["id"]), "name": row["name"],
                "created_at": row["created_at"], "token": token}

    def list_tokens(self, *, user_id: str, org_id: str) -> List[Dict[str, Any]]:
        """Lista SIN hashes ni tokens (miembros de la org)."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("select exists(select 1 from public.memberships"
                        " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
            if not cur.fetchone()["ok"]:
                return []
            cur.execute(
                "select id, name, created_at, last_used_at, revoked_at"
                " from public.ingest_tokens where org_id=%s order by created_at desc",
                (org_id,),
            )
            return [{"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"],
                     "last_used_at": r["last_used_at"], "revoked_at": r["revoked_at"]}
                    for r in cur.fetchall()]

    def revoke_token(self, *, user_id: str, token_id: str) -> bool:
        """Revoca (owner/admin de la org del token, vía la propia fila — CAS)."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update public.ingest_tokens t set revoked_at=now()"
                " where t.id=%s and t.revoked_at is null"
                "   and exists(select 1 from public.memberships m"
                "     where m.org_id=t.org_id and m.user_id=%s"
                "       and m.role in ('owner','admin'))",
                (token_id, user_id),
            )
            ok = cur.rowcount > 0
            conn.commit()
        return ok

    def resolve(self, *, token: str) -> Optional[Dict[str, str]]:
        """Autentica un token en claro → {org_id, created_by} si está activo.
        Actualiza last_used_at en la misma query (una sola ida a BD)."""
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update public.ingest_tokens set last_used_at=now()"
                " where token_hash=%s and revoked_at is null"
                " returning id, org_id, created_by",
                (_hash(token),),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        return {"token_id": str(row["id"]), "org_id": str(row["org_id"]),
                "created_by": str(row["created_by"])}
