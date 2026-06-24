import psycopg
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, repo=None, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if service is not None:
        app.dependency_overrides[api_v2.get_action_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_propose_returns_counts():
    svc = MagicMock()
    svc.propose_actions.return_value = {"quarantine": 1, "ticket": 2, "skipped": 0}
    resp = _client(service=svc).post("/v2/actions/run/r1/propose")
    assert resp.status_code == 200
    assert resp.json() == {"quarantine": 1, "ticket": 2, "skipped": 0}
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
    svc.approve_action.return_value = {"approved": True, "artifact_ref": "stub://issue/1"}
    svc.reject_action.return_value = True
    client = _client(service=svc)
    assert client.post("/v2/actions/a1/approve").json()["approved"] is True
    assert client.post("/v2/actions/a1/reject", json={"reason": "dup"}).status_code == 200
    svc.reject_action.assert_called_once_with(user_id="user-1", action_id="a1", reason="dup")


def test_propose_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/actions/run/r1/propose").status_code == 401


def test_inbox_db_error_is_502():
    repo = MagicMock()
    repo.get_actions.side_effect = psycopg.OperationalError("db")
    assert _client(repo=repo).get("/v2/actions?org_id=o1").status_code == 502
