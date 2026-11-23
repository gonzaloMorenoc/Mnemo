"""Aplicación de la matriz de permisos (src/orgs/permissions.py) en la API.

Cada endpoint que escribe pide una `Capability` con `enforce(...)`, por org o por
recurso (run, familia, acción…). El rol se lee VIVO de `memberships` en cada
petición: degradar o expulsar a alguien tiene efecto inmediato.

Los repositorios mantienen además su propia comprobación de pertenencia
(defensa en profundidad); esto añade el ROL, que antes no se miraba.
"""
import logging
from enum import Enum
from typing import Any, Optional, Protocol, Tuple

import psycopg
from fastapi import HTTPException

from src.config import multi_tenant_enabled
from src.db.pool import get_pool
from src.orgs.permissions import Capability, OrgRole, parse_role, role_allows

logger = logging.getLogger(__name__)


class Resource(str, Enum):
    RUN = "run"
    FAMILY = "family"
    ACTION = "action"
    PROPOSAL = "proposal"
    INGEST_TOKEN = "ingest_token"


# Lista blanca: el nombre de tabla NUNCA viene de la petición.
_RESOURCE_TABLE = {
    Resource.RUN: "public.test_runs",
    Resource.FAMILY: "public.defect_families",
    Resource.ACTION: "public.actions",
    Resource.PROPOSAL: "public.knowledge_proposals",
    Resource.INGEST_TOKEN: "public.ingest_tokens",
}

_DENIED_DETAIL = {
    Capability.READ: "No eres miembro de la organización",
    Capability.QA_WORK: "Tu rol es de solo lectura: pide a un admin que te suba a miembro",
    Capability.ADMIN: "Requiere rol owner/admin en la organización",
}


class AccessDenied(PermissionError):
    def __init__(self, capability: Capability):
        super().__init__(_DENIED_DETAIL[capability])
        self.capability = capability


class RoleLookup(Protocol):
    def role_of(self, *, org_id: str, user_id: str) -> Optional[str]: ...

    def org_of(self, *, resource: Resource, resource_id: str) -> Optional[str]: ...


class OrgAccessRepository:
    """Lee el rol del usuario y la org dueña de un recurso."""

    def _fetch_one(self, sql: str, params: Tuple[Any, ...]) -> Optional[dict]:
        try:
            with get_pool().connection() as conn, conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()
        except psycopg.errors.InvalidTextRepresentation:
            # UUID mal formado: no existe → sin rol / sin org (no es un 502).
            return None

    def role_of(self, *, org_id: str, user_id: str) -> Optional[str]:
        row = self._fetch_one(
            "select role::text as role from public.memberships"
            " where org_id = %s and user_id = %s",
            (org_id, user_id),
        )
        return row["role"] if row else None

    def org_of(self, *, resource: Resource, resource_id: str) -> Optional[str]:
        table = _RESOURCE_TABLE[resource]
        row = self._fetch_one(f"select org_id from {table} where id = %s", (resource_id,))
        if not row or row.get("org_id") is None:
            return None
        return str(row["org_id"])


class OrgAccess:
    def __init__(self, lookup: RoleLookup):
        self._lookup = lookup

    def require(self, *, user_id: str, capability: Capability, org_id: str) -> OrgRole:
        role = self._lookup.role_of(org_id=org_id, user_id=user_id)
        if not role_allows(role, capability):
            raise AccessDenied(capability)
        return parse_role(role)

    def require_for_resource(self, *, user_id: str, capability: Capability,
                             resource: Resource, resource_id: str) -> Optional[OrgRole]:
        """None si el recurso no existe: el endpoint responde su 404 habitual (y su
        repositorio sigue filtrando por pertenencia, así que no se filtra nada)."""
        org_id = self._lookup.org_of(resource=resource, resource_id=resource_id)
        if org_id is None:
            return None
        return self.require(user_id=user_id, capability=capability, org_id=org_id)


def _build_default_access() -> OrgAccess:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    return OrgAccess(OrgAccessRepository())


# Punto de inyección: tests/conftest.py lo sustituye para las suites que no prueban roles.
_access_factory = _build_default_access


def get_org_access() -> OrgAccess:
    """Dependencia FastAPI (override en tests con dependency_overrides)."""
    return _access_factory()


def enforce(access: OrgAccess, user_id: str, capability: Capability, *,
            org_id: Optional[str] = None,
            resource: Optional[Tuple[Resource, str]] = None) -> Optional[OrgRole]:
    """Exige `capability` y traduce el resultado a HTTP (403 / 502)."""
    if org_id is None and resource is None:
        raise ValueError("enforce necesita org_id o resource")
    try:
        if org_id is not None:
            return access.require(user_id=user_id, capability=capability, org_id=org_id)
        kind, resource_id = resource
        return access.require_for_resource(user_id=user_id, capability=capability,
                                           resource=kind, resource_id=resource_id)
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception("role lookup failed (user=%s capability=%s)", user_id, capability)
        raise HTTPException(status_code=502, detail="Database error") from exc
