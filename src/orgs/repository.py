from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row

from src.config import DATABASE_URL
from src.db.pool import get_pool


class OrganizationRepository:
    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for multi-tenant orgs endpoints")
        self.db_url = db_url

    def _connect(self):
        return get_pool().connection()

    def _set_user_claims(self, conn: psycopg.Connection, user_id: str):
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def create_organization(self, *, user_id: str, name: str) -> Dict[str, Any]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.organizations (name, created_by)
                    values (%s, %s)
                    returning id, name, join_code, created_at
                    """,
                    (name.strip(), user_id),
                )
                organization = cur.fetchone()
                # El trigger set_default_org_owner_membership crea la membership de owner;
                # reflejamos ese rol en la respuesta (el RETURNING no incluye role).
                if organization is not None:
                    organization["role"] = "owner"
            conn.commit()
        return organization

    def join_organization(self, *, user_id: str, join_code: str) -> Dict[str, Any]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select public.join_organization_by_code(%s) as org_id", (join_code.strip(),))
                row = cur.fetchone()
                if not row or not row.get("org_id"):
                    raise ValueError("Could not join organization with the provided code")
                cur.execute(
                    """
                    select o.id, o.name, o.join_code, m.role
                    from public.organizations o
                    join public.memberships m on m.org_id = o.id
                    where o.id = %s and m.user_id = %s
                    """,
                    (row["org_id"], user_id),
                )
                organization = cur.fetchone()
            conn.commit()
        return organization

    def list_user_organizations(self, *, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select o.id, o.name, o.join_code, m.role, o.created_at
                    from public.memberships m
                    join public.organizations o on o.id = m.org_id
                    where m.user_id = %s
                    order by o.created_at desc
                    """,
                    (user_id,),
                )
                return cur.fetchall()
