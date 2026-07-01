"""XrayConfig — per-org encrypted Xray credentials.

Reuses the same org_integrations table and Fernet crypto as the Jira / GitHub
integrations.  Schema additions are in db/migrations/019_xray_integration.sql.

Column mapping
--------------
  provider      = 'xray'
  base_url      = Xray host
                    Cloud  → 'https://xray.cloud.getxray.app'
                    Server → e.g. 'https://jira.acme.com'
  email         = client_id   (Cloud) or Jira email  (Server)
  api_token_enc = client_secret (Cloud) or Jira API token (Server) — Fernet-encrypted
  xray_mode     = 'cloud' | 'server'

Both cloud and server auth paths are implemented in XrayClient.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import psycopg
from cryptography.fernet import InvalidToken

from src.config import DATABASE_URL
from src.db.pool import get_pool
from src.jira.crypto import decrypt_token, encrypt_token

_CLOUD_BASE = "https://xray.cloud.getxray.app"
_DEFAULT_MODE = "cloud"


class XrayConfig:
    """Load / save per-org Xray credentials (encrypted at rest with Fernet)."""

    def __init__(self, db_url: str = DATABASE_URL) -> None:
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured")
        self.db_url = db_url

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _connect(self):
        return get_pool().connection()

    def _decrypt(self, enc: str) -> str:
        try:
            return decrypt_token(enc)
        except (InvalidToken, RuntimeError) as exc:
            raise ValueError(
                "credenciales de Xray inválidas; reconfigura la integración"
            ) from exc

    def _require_admin(self, cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s and role in ('owner','admin')) as ok",
            (org_id, user_id),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("owner/admin role required to configure Xray")

    def _require_member(self, cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s) as ok",
            (org_id, user_id),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("user is not a member of the organization")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(
        self,
        *,
        user_id: str,
        org_id: str,
        client_id: str,
        client_secret: str,
        base_url: str = _CLOUD_BASE,
        mode: str = _DEFAULT_MODE,
    ) -> None:
        """Save (insert or update) Xray credentials for the org.

        Only org owners and admins may configure integrations.
        The ``client_secret`` is encrypted with Fernet before storage.
        """
        if mode not in ("cloud", "server"):
            raise ValueError("mode must be 'cloud' or 'server'")
        enc = encrypt_token(client_secret)
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_admin(cur, org_id, user_id)
                cur.execute(
                    """
                    insert into public.org_integrations
                        (org_id, provider, base_url, email, api_token_enc, xray_mode)
                    values (%s, 'xray', %s, %s, %s, %s)
                    on conflict (org_id, provider) do update
                       set base_url      = excluded.base_url,
                           email         = excluded.email,
                           api_token_enc = excluded.api_token_enc,
                           xray_mode     = excluded.xray_mode,
                           updated_at    = now()
                    """,
                    (org_id, base_url, client_id, enc, mode),
                )
            conn.commit()

    def get(self, *, user_id: str, org_id: str) -> Optional[Dict[str, str]]:
        """Return decrypted Xray credentials for the org, or None if not set.

        Any org member may read credentials (needed to export plans).
        Returns ``{'base_url', 'client_id', 'client_secret', 'mode'}`` or ``None``.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select base_url, email, api_token_enc, xray_mode"
                    " from public.org_integrations"
                    " where org_id = %s and provider = 'xray'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "base_url": row["base_url"],
            "client_id": row["email"],
            "client_secret": self._decrypt(row["api_token_enc"]),
            "mode": row["xray_mode"] or _DEFAULT_MODE,
        }

    def get_raw(self, *, org_id: str) -> Optional[Dict[str, Any]]:
        """Return credentials without membership check (for internal use).

        Used by XrayClient when the caller has already been authorized at a
        higher layer (e.g. the API endpoint checked JWT).
        Returns ``{'base_url', 'client_id', 'client_secret', 'mode'}`` or ``None``.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select base_url, email, api_token_enc, xray_mode"
                    " from public.org_integrations"
                    " where org_id = %s and provider = 'xray'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "base_url": row["base_url"],
            "client_id": row["email"],
            "client_secret": self._decrypt(row["api_token_enc"]),
            "mode": row["xray_mode"] or _DEFAULT_MODE,
        }
