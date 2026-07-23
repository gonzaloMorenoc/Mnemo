from unittest.mock import MagicMock

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.orgs.repository import OrganizationRepository  # noqa: F401 — orgs endpoints now use this
from src.security import AuthenticatedUser


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-123", email="t@example.com", claims={})


def make_client(*, repo=None, with_user=True) -> TestClient:
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_repo] = lambda: repo
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _fake_user
    return TestClient(app)


def _org(role="member"):
    return {"id": "org-1", "name": "Acme QA", "join_code": "ABC123", "role": role, "created_at": "2026-06-19T10:00:00"}


def test_list_orgs_maps_response():
    repo = MagicMock()
    repo.list_user_organizations.return_value = [_org("owner")]
    client = make_client(repo=repo)
    resp = client.get("/v2/orgs")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "org-1"
    assert body[0]["role"] == "owner"


def test_create_org_validation_error():
    repo = MagicMock()
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "x"})  # min_length=2
    assert resp.status_code == 422


def test_create_org_happy_path():
    repo = MagicMock()
    repo.create_organization.return_value = _org("owner")
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "Acme QA"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme QA"


def test_join_org_unknown_code_returns_404():
    repo = MagicMock()
    repo.join_organization.side_effect = ValueError("Could not join organization with the provided code")
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs/join", json={"join_code": "BADCODE"})
    assert resp.status_code == 404


def test_health_reports_multi_tenant_flag(monkeypatch):
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: True)
    client = make_client(with_user=False)  # /v2/health requires no auth
    resp = client.get("/v2/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["multi_tenant_enabled"] is True
    assert "status" in body


def test_health_incluye_el_modelo_de_ia(monkeypatch):
    """El frontend (Ajustes) muestra 'Modelo de IA' desde este campo; antes faltaba
    y salía en blanco."""
    monkeypatch.setattr(api_v2, "resolved_model_name", lambda: "gemini-2.0-flash")
    client = make_client(with_user=False)
    resp = client.get("/v2/health")
    assert resp.status_code == 200
    assert resp.json()["model"] == "gemini-2.0-flash"


def test_list_orgs_db_error_returns_502():
    repo = MagicMock()
    repo.list_user_organizations.side_effect = psycopg.OperationalError("boom")
    client = make_client(repo=repo)
    resp = client.get("/v2/orgs")
    assert resp.status_code == 502


def test_create_org_none_result_returns_502():
    repo = MagicMock()
    repo.create_organization.return_value = None
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "Acme QA"})
    assert resp.status_code == 502


def test_join_org_none_result_returns_502():
    repo = MagicMock()
    repo.join_organization.return_value = None
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs/join", json={"join_code": "ABC123"})
    assert resp.status_code == 502


