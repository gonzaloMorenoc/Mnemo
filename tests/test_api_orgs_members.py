"""Endpoints de gestión de miembros y del código de unión (auditoría 23-nov, #11 / H3)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.orgs import api as orgs_api
from src.orgs.member_rules import LastOwnerError, MemberActionForbidden
from src.orgs.repository import MemberNotFound
from src.security import AuthenticatedUser

EXPIRES = datetime(2026, 12, 1, tzinfo=timezone.utc)


def _client(repo):
    app = FastAPI()
    app.include_router(orgs_api.router)
    app.dependency_overrides[orgs_api.get_current_user] = lambda: AuthenticatedUser(
        user_id="admin-1", email="a@x.com", claims={})
    app.dependency_overrides[api_v2.get_repo] = lambda: repo
    return TestClient(app)


def test_list_members():
    repo = MagicMock()
    repo.list_members.return_value = [
        {"user_id": "u2", "role": "viewer", "email": "v@x.com", "display_name": None,
         "created_at": EXPIRES}]
    resp = _client(repo).get("/v2/orgs/o1/members")
    assert resp.status_code == 200
    assert resp.json() == [{"user_id": "u2", "role": "viewer", "email": "v@x.com",
                            "display_name": None, "created_at": EXPIRES.isoformat()}]
    repo.list_members.assert_called_once_with(actor_id="admin-1", org_id="o1")


def test_list_members_forbidden_for_non_admin():
    repo = MagicMock()
    repo.list_members.side_effect = MemberActionForbidden("requiere rol owner/admin")
    assert _client(repo).get("/v2/orgs/o1/members").status_code == 403


def test_change_role():
    repo = MagicMock()
    repo.change_member_role.return_value = {"user_id": "u2", "role": "member"}
    resp = _client(repo).patch("/v2/orgs/o1/members/u2", json={"role": "member"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "u2", "role": "member"}
    repo.change_member_role.assert_called_once_with(
        actor_id="admin-1", org_id="o1", target_id="u2", new_role="member")


def test_change_role_rejects_unknown_roles_before_the_db():
    repo = MagicMock()
    resp = _client(repo).patch("/v2/orgs/o1/members/u2", json={"role": "superuser"})
    assert resp.status_code == 422
    repo.change_member_role.assert_not_called()


@pytest.mark.parametrize("exc,status", [
    (MemberActionForbidden("un admin no puede modificar a un owner"), 403),
    (LastOwnerError("la organización no puede quedarse sin owner"), 409),
    (MemberNotFound("no es miembro"), 404),
    (psycopg.OperationalError("down"), 502),
])
def test_change_role_error_mapping(exc, status):
    repo = MagicMock()
    repo.change_member_role.side_effect = exc
    resp = _client(repo).patch("/v2/orgs/o1/members/u2", json={"role": "viewer"})
    assert resp.status_code == status


def test_remove_member():
    repo = MagicMock()
    resp = _client(repo).delete("/v2/orgs/o1/members/u2")
    assert resp.status_code == 200
    assert resp.json() == {"removed": True}
    repo.remove_member.assert_called_once_with(actor_id="admin-1", org_id="o1", target_id="u2")


@pytest.mark.parametrize("exc,status", [
    (MemberActionForbidden("x"), 403),
    (LastOwnerError("x"), 409),
    (MemberNotFound("x"), 404),
])
def test_remove_member_error_mapping(exc, status):
    repo = MagicMock()
    repo.remove_member.side_effect = exc
    assert _client(repo).delete("/v2/orgs/o1/members/u2").status_code == status


def test_rotate_join_code():
    repo = MagicMock()
    repo.rotate_join_code.return_value = {"join_code": "a1b2c3d4e5f6",
                                          "join_code_expires_at": EXPIRES}
    resp = _client(repo).post("/v2/orgs/o1/join-code/rotate")
    assert resp.status_code == 200
    assert resp.json() == {"join_code": "a1b2c3d4e5f6",
                           "join_code_expires_at": EXPIRES.isoformat()}
    repo.rotate_join_code.assert_called_once_with(actor_id="admin-1", org_id="o1")


def test_rotate_join_code_forbidden_for_non_admin():
    repo = MagicMock()
    repo.rotate_join_code.side_effect = MemberActionForbidden("requiere rol owner/admin")
    assert _client(repo).post("/v2/orgs/o1/join-code/rotate").status_code == 403


def test_requires_auth():
    app = FastAPI()
    app.include_router(orgs_api.router)
    app.dependency_overrides[api_v2.get_repo] = lambda: MagicMock()
    assert TestClient(app).get("/v2/orgs/o1/members").status_code == 401


def test_router_is_mounted_in_the_app():
    from asgi import app
    paths = {route.path for route in app.routes}
    assert "/v2/orgs/{org_id}/members" in paths
    assert "/v2/orgs/{org_id}/join-code/rotate" in paths


# --- La respuesta de /v2/orgs ya no expone el código a quien no es admin ----------------

def test_orgs_response_allows_hidden_join_code():
    repo = MagicMock()
    repo.list_user_organizations.return_value = [
        {"id": "o1", "name": "Acme", "join_code": None, "join_code_expires_at": None,
         "role": "viewer", "created_at": None}]
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id="u", email=None, claims={})
    app.dependency_overrides[api_v2.get_repo] = lambda: repo
    body = TestClient(app).get("/v2/orgs").json()
    assert body[0]["join_code"] is None
    assert body[0]["role"] == "viewer"


def test_orgs_response_includes_expiry_for_admins():
    repo = MagicMock()
    repo.list_user_organizations.return_value = [
        {"id": "o1", "name": "Acme", "join_code": "abc", "join_code_expires_at": EXPIRES,
         "role": "owner", "created_at": None}]
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id="u", email=None, claims={})
    app.dependency_overrides[api_v2.get_repo] = lambda: repo
    body = TestClient(app).get("/v2/orgs").json()
    assert body[0]["join_code_expires_at"] == EXPIRES.isoformat()
