"""OrgAccess: aplica la matriz de permisos con el rol vivo de la BD."""
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi import HTTPException

from src.orgs.access import (
    AccessDenied,
    OrgAccess,
    OrgAccessRepository,
    Resource,
    enforce,
)
from src.orgs.permissions import Capability, OrgRole


class _Lookup:
    def __init__(self, roles=None, orgs=None):
        self.roles = roles or {}
        self.orgs = orgs or {}

    def role_of(self, *, org_id, user_id):
        return self.roles.get((org_id, user_id))

    def org_of(self, *, resource, resource_id):
        return self.orgs.get((resource, resource_id))


def test_require_returns_role_when_allowed():
    access = OrgAccess(_Lookup(roles={("o1", "u1"): "member"}))
    assert access.require(user_id="u1", capability=Capability.QA_WORK, org_id="o1") is OrgRole.MEMBER


def test_require_denies_viewer_writes():
    access = OrgAccess(_Lookup(roles={("o1", "u1"): "viewer"}))
    with pytest.raises(AccessDenied):
        access.require(user_id="u1", capability=Capability.QA_WORK, org_id="o1")


def test_require_denies_non_members():
    access = OrgAccess(_Lookup())
    with pytest.raises(AccessDenied):
        access.require(user_id="u1", capability=Capability.READ, org_id="o1")


def test_resource_is_resolved_to_its_org():
    lookup = _Lookup(roles={("o1", "u1"): "member"}, orgs={(Resource.RUN, "r1"): "o1"})
    access = OrgAccess(lookup)
    with pytest.raises(AccessDenied):
        access.require_for_resource(user_id="u1", capability=Capability.ADMIN,
                                    resource=Resource.RUN, resource_id="r1")


def test_unknown_resource_defers_to_the_endpoint():
    """Recurso inexistente: no hay org que mirar; el endpoint responde su 404 de siempre."""
    access = OrgAccess(_Lookup())
    assert access.require_for_resource(user_id="u1", capability=Capability.ADMIN,
                                       resource=Resource.RUN, resource_id="nope") is None


def test_enforce_maps_denial_to_403():
    access = OrgAccess(_Lookup(roles={("o1", "u1"): "viewer"}))
    with pytest.raises(HTTPException) as exc:
        enforce(access, "u1", Capability.QA_WORK, org_id="o1")
    assert exc.value.status_code == 403


def test_enforce_maps_db_errors_to_502():
    lookup = MagicMock()
    lookup.role_of.side_effect = psycopg.OperationalError("down")
    with pytest.raises(HTTPException) as exc:
        enforce(OrgAccess(lookup), "u1", Capability.QA_WORK, org_id="o1")
    assert exc.value.status_code == 502


def test_enforce_requires_org_or_resource():
    with pytest.raises(ValueError):
        enforce(OrgAccess(_Lookup()), "u1", Capability.QA_WORK)


def test_enforce_with_resource():
    lookup = _Lookup(roles={("o1", "u1"): "admin"}, orgs={(Resource.ACTION, "a1"): "o1"})
    assert enforce(OrgAccess(lookup), "u1", Capability.ADMIN,
                   resource=(Resource.ACTION, "a1")) is OrgRole.ADMIN


def _fake_pool(row):
    cur = MagicMock()
    cur.fetchone.return_value = row
    cur.__enter__.return_value = cur
    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__.return_value = conn
    pool = MagicMock()
    pool.connection.return_value = conn
    return pool, cur


def test_repository_role_of(monkeypatch):
    pool, cur = _fake_pool({"role": "viewer"})
    monkeypatch.setattr("src.orgs.access.get_pool", lambda: pool)
    repo = OrgAccessRepository()
    assert repo.role_of(org_id="o1", user_id="u1") == "viewer"
    assert cur.execute.call_args[0][1] == ("o1", "u1")


def test_repository_role_of_none_when_not_member(monkeypatch):
    pool, _ = _fake_pool(None)
    monkeypatch.setattr("src.orgs.access.get_pool", lambda: pool)
    assert OrgAccessRepository().role_of(org_id="o1", user_id="u1") is None


@pytest.mark.parametrize("resource,table", [
    (Resource.RUN, "public.test_runs"),
    (Resource.FAMILY, "public.defect_families"),
    (Resource.ACTION, "public.actions"),
    (Resource.PROPOSAL, "public.knowledge_proposals"),
    (Resource.INGEST_TOKEN, "public.ingest_tokens"),
])
def test_repository_org_of_uses_whitelisted_table(monkeypatch, resource, table):
    pool, cur = _fake_pool({"org_id": "o9"})
    monkeypatch.setattr("src.orgs.access.get_pool", lambda: pool)
    assert OrgAccessRepository().org_of(resource=resource, resource_id="x") == "o9"
    assert table in cur.execute.call_args[0][0]


def test_repository_org_of_invalid_uuid_is_none(monkeypatch):
    pool, cur = _fake_pool(None)
    cur.execute.side_effect = psycopg.errors.InvalidTextRepresentation("bad uuid")
    monkeypatch.setattr("src.orgs.access.get_pool", lambda: pool)
    assert OrgAccessRepository().org_of(resource=Resource.RUN, resource_id="nope") is None


def test_default_access_needs_multitenant(monkeypatch):
    from src.orgs import access as access_module
    monkeypatch.setattr(access_module, "multi_tenant_enabled", lambda: False)
    with pytest.raises(HTTPException) as exc:
        access_module._build_default_access()
    assert exc.value.status_code == 503


def test_default_access_uses_repository(monkeypatch):
    from src.orgs import access as access_module
    monkeypatch.setattr(access_module, "multi_tenant_enabled", lambda: True)
    assert isinstance(access_module._build_default_access()._lookup, OrgAccessRepository)
