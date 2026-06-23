import psycopg
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(repo, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_triage_run_returns_verdicts():
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [
        {"id": "v1", "failure_id": "f1", "category": "real", "confidence": 0.85,
         "rule_applied": "R4_real_recurrent", "evidence_bundle": {"k": "v"},
         "requires_approval": False, "llm_assisted": False, "status": "resolved"},
    ]
    client = make_client(repo)
    resp = client.get("/v2/triage/run/r1")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["category"] == "real" and body[0]["status"] == "resolved"
    assert body[0]["evidence_bundle"] == {"k": "v"}
    assert body[0]["failure_id"] == "f1" and body[0]["confidence"] == 0.85
    assert body[0]["rule_applied"] == "R4_real_recurrent"
    assert body[0]["requires_approval"] is False and body[0]["llm_assisted"] is False


def test_triage_run_requires_auth():
    client = make_client(MagicMock(), with_user=False)
    assert client.get("/v2/triage/run/r1").status_code == 401


def test_triage_run_db_error_is_502():
    repo = MagicMock()
    repo.get_triage_for_run.side_effect = psycopg.OperationalError("db down")
    client = make_client(repo)
    assert client.get("/v2/triage/run/r1").status_code == 502


def test_resolve_endpoint_returns_summary():
    svc = MagicMock()
    svc.resolve_tiebreaks.return_value = {"resolved": 2, "pending": 1}
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_triage_service] = lambda: svc
    app.dependency_overrides[api_v2.get_current_user] = _user
    client = TestClient(app)
    resp = client.post("/v2/triage/run/r1/resolve")
    assert resp.status_code == 200
    assert resp.json() == {"resolved": 2, "pending": 1}
    svc.resolve_tiebreaks.assert_called_once_with(user_id="user-1", run_id="r1")


def test_resolve_endpoint_requires_auth():
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_triage_service] = lambda: MagicMock()
    client = TestClient(app)  # sin override de usuario → 401
    assert client.post("/v2/triage/run/r1/resolve").status_code == 401


def test_resolve_endpoint_db_error_is_502():
    svc = MagicMock()
    svc.resolve_tiebreaks.side_effect = psycopg.OperationalError("db down")
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_triage_service] = lambda: svc
    app.dependency_overrides[api_v2.get_current_user] = _user
    client = TestClient(app)
    assert client.post("/v2/triage/run/r1/resolve").status_code == 502
