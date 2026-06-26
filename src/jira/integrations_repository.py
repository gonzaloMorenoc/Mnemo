from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row
from cryptography.fernet import InvalidToken

from src.config import DATABASE_URL
from src.jira.crypto import decrypt_token, encrypt_token


class IntegrationsRepository:
    """Credenciales de integraciones por org. El pooler bypassa RLS, así que el
    aislamiento es por membership en cada consulta. El token va cifrado (Fernet)."""

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.db_url, row_factory=dict_row)

    def _decrypt(self, enc: str) -> str:
        """Descifra un token cifrado con Fernet.

        Convierte InvalidToken (clave rotada / cifrado corrupto) y RuntimeError
        (clave ausente) en ValueError para que el endpoint pueda responder 400
        en lugar de propagar un 500 con stacktrace.
        """
        try:
            return decrypt_token(enc)
        except (InvalidToken, RuntimeError) as exc:
            raise ValueError(
                "credenciales de Jira inválidas; reconfigura la integración"
            ) from exc

    def _require_member(self, cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s) as ok",
            (org_id, user_id),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("user is not a member of the organization")

    def _require_admin(self, cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s and role in ('owner','admin')) as ok",
            (org_id, user_id),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("owner/admin role required to configure integrations")

    def upsert_jira_config(self, *, user_id: str, org_id: str, base_url: str,
                           email: str, token: str, jql: str) -> None:
        enc = encrypt_token(token)
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_admin(cur, org_id, user_id)
                cur.execute(
                    """
                    insert into public.org_integrations
                        (org_id, provider, base_url, email, api_token_enc, jql)
                    values (%s, 'jira', %s, %s, %s, %s)
                    on conflict (org_id, provider) do update
                       set base_url = excluded.base_url,
                           email = excluded.email,
                           api_token_enc = excluded.api_token_enc,
                           jql = excluded.jql,
                           updated_at = now()
                    """,
                    (org_id, base_url, email, enc, jql),
                )
            conn.commit()

    def get_jira_config(self, *, user_id: str, org_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select base_url, email, jql from public.org_integrations"
                    " where org_id = %s and provider = 'jira'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return {"configured": False, "base_url": None, "email": None, "jql": None}
        return {"configured": True, "base_url": row["base_url"],
                "email": row["email"], "jql": row["jql"]}

    def upsert_github_config(self, *, user_id: str, org_id: str,
                             installation_id: str, repo_full_name: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_admin(cur, org_id, user_id)
                cur.execute(
                    """
                    insert into public.org_integrations
                        (org_id, provider, base_url, installation_id, repo_full_name)
                    values (%s, 'github', 'https://github.com', %s, %s)
                    on conflict (org_id, provider) do update
                       set installation_id = excluded.installation_id,
                           repo_full_name = excluded.repo_full_name,
                           updated_at = now()
                    """,
                    (org_id, installation_id, repo_full_name),
                )
            conn.commit()

    def get_github_config(self, *, user_id: str, org_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select installation_id, repo_full_name from public.org_integrations"
                    " where org_id = %s and provider = 'github'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return {"configured": False, "repo_full_name": None, "installation_id": None}
        return {"configured": True, "repo_full_name": row["repo_full_name"],
                "installation_id": row["installation_id"]}

    def get_jira_credentials(self, *, user_id: str, org_id: str) -> Optional[Dict[str, str]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select base_url, email, api_token_enc, jql"
                    " from public.org_integrations where org_id = %s and provider = 'jira'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"base_url": row["base_url"], "email": row["email"],
                "token": self._decrypt(row["api_token_enc"]), "jql": row["jql"]}
