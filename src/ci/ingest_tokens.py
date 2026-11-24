"""Tokens de ingesta CI por organización (public.ingest_tokens).

Formato del token: `mnemo_it_<48 hex>` (ingesta) o `mnemo_rt_<48 hex>` (solo lectura,
para asistentes de IA por MCP; migración 037). En BD solo vive el sha256; el claro se
devuelve UNA vez al crear. Cada token tiene UN ámbito (`scopes`), opcionalmente un
proyecto al que se limita y una caducidad.

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
READ_TOKEN_PREFIX = "mnemo_rt_"
SCOPE_INGEST = "ingest"
SCOPE_READ = "read"
PREFIX_BY_SCOPE = {SCOPE_INGEST: TOKEN_PREFIX, SCOPE_READ: READ_TOKEN_PREFIX}


class UnknownProject(ValueError):
    """El proyecto al que se quiere atar el token no existe (o está archivado)."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IngestTokenRepository:
    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return get_pool().connection()

    def create_token(self, *, user_id: str, org_id: str, name: str,
                     scope: str = SCOPE_INGEST, project: Optional[str] = None,
                     expires_in_days: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Crea un token (owner/admin). Devuelve el token EN CLARO (única vez).
        None si no es owner/admin; UnknownProject si el proyecto no existe."""
        token = PREFIX_BY_SCOPE[scope] + secrets.token_hex(24)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select exists(select 1 from public.memberships"
                " where org_id=%s and user_id=%s and role in ('owner','admin')) as ok",
                (org_id, user_id),
            )
            if not cur.fetchone()["ok"]:
                return None
            if project is not None:
                cur.execute("select exists(select 1 from public.projects where org_id=%s"
                            " and key=%s and archived_at is null) as ok", (org_id, project))
                if not cur.fetchone()["ok"]:
                    raise UnknownProject(project)
            cur.execute(
                "insert into public.ingest_tokens"
                " (org_id, name, token_hash, created_by, scopes, project, expires_at)"
                " values (%s,%s,%s,%s,%s,%s,"
                "  case when %s::int is null then null else now() + make_interval(days => %s::int) end)"
                " returning id, name, created_at, scopes, project, expires_at",
                (org_id, name, _hash(token), user_id, [scope], project,
                 expires_in_days, expires_in_days),
            )
            row = cur.fetchone()
            conn.commit()
        return {**_public_row(row), "token": token}

    def list_tokens(self, *, user_id: str, org_id: str,
                    scope: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista SIN hashes ni tokens (miembros de la org). Con `scope`, solo ese ámbito."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("select exists(select 1 from public.memberships"
                        " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
            if not cur.fetchone()["ok"]:
                return []
            cur.execute(
                "select id, name, created_at, last_used_at, revoked_at, scopes, project,"
                " expires_at from public.ingest_tokens"
                " where org_id=%s and (%s::text is null or %s::text = any(scopes))"
                " order by created_at desc",
                (org_id, scope, scope),
            )
            return [_public_row(r) for r in cur.fetchall()]

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

    def resolve(self, *, token: str, scope: str = SCOPE_INGEST) -> Optional[Dict[str, Any]]:
        """Autentica un token en claro → {token_id, org_id, created_by, acting_user_id,
        project} si está activo PARA ESE ÁMBITO (None si no existe, está revocado o
        caducado, o es de otro ámbito). Actualiza last_used_at en la misma query (una
        sola ida a BD). `acting_user_id` es None si la org no tiene ningún owner/admin
        vigente (el endpoint responde 403)."""
        prefix = PREFIX_BY_SCOPE.get(scope)
        if not token or not prefix or not token.startswith(prefix):
            return None
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "with tok as ("
                "  update public.ingest_tokens set last_used_at=now()"
                "  where token_hash=%s and revoked_at is null and %s = any(scopes)"
                "    and (expires_at is null or expires_at > now())"
                "  returning id, org_id, created_by, project"
                ")"
                " select tok.id, tok.org_id, tok.created_by, tok.project,"
                "  (select m.user_id from public.memberships m"
                "    where m.org_id = tok.org_id and m.role in ('owner','admin')"
                "    order by (m.user_id = tok.created_by) desc, (m.role = 'owner') desc,"
                "             m.created_at, m.user_id"
                "    limit 1) as acting_user_id"
                " from tok",
                (_hash(token), scope),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            return None
        acting = row["acting_user_id"]
        return {"token_id": str(row["id"]), "org_id": str(row["org_id"]),
                "created_by": str(row["created_by"]),
                "acting_user_id": str(acting) if acting else None,
                "project": row.get("project")}


def _public_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """Lo que se puede enseñar de un token (nunca el hash)."""
    scopes = list(r.get("scopes") or [SCOPE_INGEST])
    return {"id": str(r["id"]), "name": r["name"], "created_at": r["created_at"],
            "last_used_at": r.get("last_used_at"), "revoked_at": r.get("revoked_at"),
            "scope": scopes[0], "project": r.get("project"),
            "expires_at": r.get("expires_at")}
