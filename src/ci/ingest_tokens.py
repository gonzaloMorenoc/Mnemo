"""Tokens de ingesta CI por organización (public.ingest_tokens).

Formato del token: `mnemo_it_<48 hex>`. En BD solo vive el sha256; el claro se
devuelve UNA vez al crear.

El token es una credencial DE LA ORGANIZACIÓN, no de la persona que lo creó: la
ingesta se autoriza por la org del token (válido y no revocado). Antes corría como
`created_by` y, si esa persona dejaba la org, el CI empezaba a dar 403 — el factor
autobús que Mnemo promete resolver (auditoría 23-nov, #6).

El pipeline posterior (triaje, acta, gate, propuestas) vive en repositorios que
aíslan por membresía en la capa de app; para no abrir en todos ellos una vía «sin
usuario», `resolve` elige el ACTOR técnico con el que corre: el creador si sigue
siendo owner/admin de la org y, si no, el owner (después el admin) vigente más
antiguo. No es una escalada: el token solo da acceso a `/v2/ci/ingest`, cuyas
acciones son fijas, y quien lo creó ya tenía que ser owner/admin. `created_by` se
conserva solo para auditoría. Cortar el acceso = revocar el token (explícito).
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

    def resolve(self, *, token: str) -> Optional[Dict[str, Any]]:
        """Autentica un token en claro → {token_id, org_id, created_by, acting_user_id}
        si está activo (None si no existe o está revocado). Actualiza last_used_at en
        la misma query (una sola ida a BD). `acting_user_id` es None si la org no
        tiene ningún owner/admin vigente (el endpoint responde 403)."""
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "with tok as ("
                "  update public.ingest_tokens set last_used_at=now()"
                "  where token_hash=%s and revoked_at is null"
                "  returning id, org_id, created_by"
                ")"
                " select tok.id, tok.org_id, tok.created_by,"
                "  (select m.user_id from public.memberships m"
                "    where m.org_id = tok.org_id and m.role in ('owner','admin')"
                "    order by (m.user_id = tok.created_by) desc, (m.role = 'owner') desc,"
                "             m.created_at, m.user_id"
                "    limit 1) as acting_user_id"
                " from tok",
                (_hash(token),),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        acting = row["acting_user_id"]
        return {"token_id": str(row["id"]), "org_id": str(row["org_id"]),
                "created_by": str(row["created_by"]),
                "acting_user_id": str(acting) if acting else None}
