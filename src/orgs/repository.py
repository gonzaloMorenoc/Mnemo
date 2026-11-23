import secrets
from typing import Any, Dict, List, Optional

import psycopg

from src.config import DATABASE_URL
from src.db.pool import get_pool
from src.orgs.member_rules import MemberActionForbidden, check_removal, check_role_change
from src.orgs.permissions import Capability, OrgRole, role_allows

# Caducidad del código de unión al rotarlo. Mismo valor que el DEFAULT de la
# columna en db/migrations/032_join_code_viewer_expiry.sql.
JOIN_CODE_TTL_DAYS = 7
# 6 bytes = 12 hex (48 bits): más margen que los 10 hex originales frente a fuerza bruta.
JOIN_CODE_BYTES = 6

_JOIN_ERRORS = {
    "expired join code": "El código de invitación ha caducado: pide uno nuevo a un admin",
    "invalid join code": "Código de invitación no válido",
}
_JOIN_ERROR_DEFAULT = "Could not join organization with the provided code"


class MemberNotFound(LookupError):
    """El usuario indicado no es miembro de la organización."""


def _with_visible_join_code(row: Dict[str, Any]) -> Dict[str, Any]:
    """El código de unión solo lo ven owner/admin (antes lo veía cualquier miembro)."""
    if role_allows(row.get("role"), Capability.ADMIN):
        return dict(row)
    return {**row, "join_code": None, "join_code_expires_at": None}


def _join_error_message(exc: psycopg.Error) -> str:
    text = str(exc)
    return next((msg for key, msg in _JOIN_ERRORS.items() if key in text), _JOIN_ERROR_DEFAULT)


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
                    returning id, name, join_code, join_code_expires_at, created_at
                    """,
                    (name.strip(), user_id),
                )
                organization = cur.fetchone()
                # El trigger set_default_org_owner_membership crea la membership de owner;
                # reflejamos ese rol en la respuesta (el RETURNING no incluye role).
                if organization is not None:
                    organization = {**organization, "role": OrgRole.OWNER.value}
            conn.commit()
        return organization

    def join_organization(self, *, user_id: str, join_code: str) -> Dict[str, Any]:
        """Entra como viewer (lo decide join_organization_by_code, migración 032)."""
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                try:
                    cur.execute("select public.join_organization_by_code(%s) as org_id",
                                (join_code.strip(),))
                except psycopg.errors.RaiseException as exc:
                    raise ValueError(_join_error_message(exc)) from exc
                row = cur.fetchone()
                if not row or not row.get("org_id"):
                    raise ValueError(_JOIN_ERROR_DEFAULT)
                cur.execute(
                    """
                    select o.id, o.name, o.join_code, o.join_code_expires_at, m.role
                    from public.organizations o
                    join public.memberships m on m.org_id = o.id
                    where o.id = %s and m.user_id = %s
                    """,
                    (row["org_id"], user_id),
                )
                organization = cur.fetchone()
            conn.commit()
        return _with_visible_join_code(organization) if organization else organization

    def list_user_organizations(self, *, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_user_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select o.id, o.name, o.join_code, o.join_code_expires_at, m.role,
                           o.created_at
                    from public.memberships m
                    join public.organizations o on o.id = m.org_id
                    where m.user_id = %s
                    order by o.created_at desc
                    """,
                    (user_id,),
                )
                return [_with_visible_join_code(r) for r in cur.fetchall()]

    # --- Gestión del código y de los miembros (owner/admin) -------------------------

    @staticmethod
    def _role_of(cur, org_id: str, user_id: str) -> Optional[str]:
        cur.execute(
            "select role::text as role from public.memberships where org_id = %s and user_id = %s",
            (org_id, user_id),
        )
        row = cur.fetchone()
        return row["role"] if row else None

    @classmethod
    def _require_admin(cls, cur, org_id: str, user_id: str) -> None:
        if not role_allows(cls._role_of(cur, org_id, user_id), Capability.ADMIN):
            raise MemberActionForbidden("requiere rol owner/admin en la organización")

    @staticmethod
    def _lock_members(cur, org_id: str) -> Dict[str, str]:
        """Bloquea las membresías de la org: dos admins a la vez no pueden dejarla sin owner."""
        cur.execute(
            "select user_id::text as user_id, role::text as role from public.memberships"
            " where org_id = %s for update",
            (org_id,),
        )
        return {r["user_id"]: r["role"] for r in cur.fetchall()}

    @staticmethod
    def _owner_count(members: Dict[str, str]) -> int:
        return sum(1 for role in members.values() if role == OrgRole.OWNER.value)

    def rotate_join_code(self, *, actor_id: str, org_id: str) -> Dict[str, Any]:
        new_code = secrets.token_hex(JOIN_CODE_BYTES)
        with self._connect() as conn, conn.cursor() as cur:
            self._require_admin(cur, org_id, actor_id)
            cur.execute(
                """
                update public.organizations
                   set join_code = %s,
                       join_code_expires_at = now() + make_interval(days => %s)
                 where id = %s
                returning join_code, join_code_expires_at
                """,
                (new_code, JOIN_CODE_TTL_DAYS, org_id),
            )
            row = cur.fetchone()
            conn.commit()
        return dict(row)

    def list_members(self, *, actor_id: str, org_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            self._require_admin(cur, org_id, actor_id)
            cur.execute(
                """
                select m.user_id::text as user_id, m.role::text as role, m.created_at,
                       u.email, p.display_name
                from public.memberships m
                left join auth.users u on u.id = m.user_id
                left join public.profiles p on p.user_id = m.user_id
                where m.org_id = %s
                order by array_position(array['owner','admin','member','viewer'], m.role::text),
                         m.created_at
                """,
                (org_id,),
            )
            return cur.fetchall()

    def change_member_role(self, *, actor_id: str, org_id: str, target_id: str,
                           new_role: str) -> Dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            members = self._lock_members(cur, org_id)
            if target_id not in members:
                raise MemberNotFound("el usuario no es miembro de la organización")
            role = check_role_change(
                actor_role=members.get(actor_id), target_role=members[target_id],
                new_role=new_role, is_self=actor_id == target_id,
                owner_count=self._owner_count(members),
            )
            cur.execute(
                "update public.memberships set role = %s where org_id = %s and user_id = %s"
                " returning user_id::text as user_id, role::text as role",
                (role.value, org_id, target_id),
            )
            row = cur.fetchone()
            conn.commit()
        return dict(row)

    def remove_member(self, *, actor_id: str, org_id: str, target_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            members = self._lock_members(cur, org_id)
            if target_id not in members:
                raise MemberNotFound("el usuario no es miembro de la organización")
            check_removal(
                actor_role=members.get(actor_id), target_role=members[target_id],
                is_self=actor_id == target_id, owner_count=self._owner_count(members),
            )
            cur.execute(
                "delete from public.memberships where org_id = %s and user_id = %s",
                (org_id, target_id),
            )
            conn.commit()
