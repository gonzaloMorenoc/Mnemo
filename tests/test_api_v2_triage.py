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


def test_triage_run_requires_auth():
    client = make_client(MagicMock(), with_user=False)
    assert client.get("/v2/triage/run/r1").status_code == 401


def test_triage_run_db_error_is_502():
    repo = MagicMock()
    repo.get_triage_for_run.side_effect = psycopg.OperationalError("db down")
    client = make_client(repo)
    assert client.get("/v2/triage/run/r1").status_code == 502
