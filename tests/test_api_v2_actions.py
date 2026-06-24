import psycopg
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, repo=None, service=None, integrations=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
        app.dependency_overrides[api_v2.get_action_repo] = lambda: repo
    if service is not None:
        app.dependency_overrides[api_v2.get_action_service] = lambda: service
    if integrations is not None:
        app.dependency_overrides[api_v2.get_integrations_repo] = lambda: integrations
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_propose_returns_counts():
    svc = MagicMock()
    svc.propose_actions.return_value = {"quarantine": 1, "ticket": 2, "self_heal": 0, "skipped": 0}
    resp = _client(service=svc).post("/v2/actions/run/r1/propose")
    assert resp.status_code == 200
    assert resp.json() == {"quarantine": 1, "ticket": 2, "self_heal": 0, "skipped": 0}
    svc.propose_actions.assert_called_once_with(user_id="user-1", run_id="r1")


def test_inbox_returns_actions():
    repo = MagicMock()
    repo.get_actions.return_value = [{"id": "a1", "triage_verdict_id": "v1", "run_id": "r1",
        "kind": "ticket", "payload": {"title": "T"}, "summary": "s", "status": "proposed",
        "artifact_ref": None, "approved_by": None, "approved_at": None, "reject_reason": None}]
    resp = _client(repo=repo).get("/v2/actions?org_id=o1&status=proposed")
    assert resp.status_code == 200 and resp.json()[0]["kind"] == "ticket"
    repo.get_actions.assert_called_once_with(user_id="user-1", org_id="o1", status="proposed")


def test_approve_and_reject():
    svc = MagicMock()
    svc.approve_action.return_value = {"approved": True, "materialized": True,
                                       "artifact_ref": "https://github.com/o/r/issues/1"}
    svc.reject_action.return_value = True
    client = _client(service=svc)
    approve_resp = client.post("/v2/actions/a1/approve")
    assert approve_resp.status_code == 200
    body = approve_resp.json()
    assert body["approved"] is True and body["materialized"] is True
    assert client.post("/v2/actions/a1/reject", json={"reason": "dup"}).status_code == 200
    svc.approve_action.assert_called_once_with(user_id="user-1", action_id="a1")
    svc.reject_action.assert_called_once_with(user_id="user-1", action_id="a1", reason="dup")


def test_approve_github_not_configured_is_400():
    svc = MagicMock()
    svc.approve_action.side_effect = ValueError("GitHub no configurado para el org")
    assert _client(service=svc).post("/v2/actions/a1/approve").status_code == 400


def test_approve_github_api_error_is_502():
    from src.ci.github_app import GitHubError
    svc = MagicMock()
    svc.approve_action.side_effect = GitHubError("boom")
    assert _client(service=svc).post("/v2/actions/a1/approve").status_code == 502


def test_approve_github_app_unconfigured_is_503():
    from src.ci.github_auth import GitHubAuthError
    svc = MagicMock()
    svc.approve_action.side_effect = GitHubAuthError("no app")
    assert _client(service=svc).post("/v2/actions/a1/approve").status_code == 503


def test_list_actions_invalid_status_is_400():
    assert _client(repo=MagicMock()).get("/v2/actions?org_id=o1&status=bogus").status_code == 400


def test_propose_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/actions/run/r1/propose").status_code == 401


def test_inbox_db_error_is_502():
    repo = MagicMock()
    repo.get_actions.side_effect = psycopg.OperationalError("db")
    assert _client(repo=repo).get("/v2/actions?org_id=o1").status_code == 502


def test_approve_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/actions/a1/approve").status_code == 401


def test_reject_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post(
        "/v2/actions/a1/reject", json={"reason": "x"}).status_code == 401


def test_inbox_requires_auth():
    assert _client(repo=MagicMock(), with_user=False).get("/v2/actions?org_id=o1").status_code == 401


def test_set_github_integration():
    integ = MagicMock()
    resp = _client(integrations=integ).post(
        "/v2/integrations/github",
        json={"org_id": "o1", "installation_id": "42", "repo_full_name": "acme/web"})
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "repo_full_name": "acme/web", "installation_id": "42"}
    integ.upsert_github_config.assert_called_once_with(
        user_id="user-1", org_id="o1", installation_id="42", repo_full_name="acme/web")


def test_get_github_integration():
    integ = MagicMock()
    integ.get_github_config.return_value = {"configured": True, "repo_full_name": "acme/web",
                                            "installation_id": "42"}
    resp = _client(integrations=integ).get("/v2/integrations/github?org_id=o1")
    assert resp.status_code == 200 and resp.json()["repo_full_name"] == "acme/web"


def test_set_github_integration_non_member_403():
    integ = MagicMock()
    integ.upsert_github_config.side_effect = PermissionError("nope")
    resp = _client(integrations=integ).post(
        "/v2/integrations/github",
        json={"org_id": "o1", "installation_id": "42", "repo_full_name": "acme/web"})
    assert resp.status_code == 403


def test_set_github_integration_requires_auth():
    assert _client(integrations=MagicMock(), with_user=False).post(
        "/v2/integrations/github",
        json={"org_id": "o", "installation_id": "1", "repo_full_name": "a/b"}).status_code == 401
