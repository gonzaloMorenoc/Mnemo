from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg

import src.api_v2 as api_v2
from src.ci.github_app import GitHubError
from src.ci.github_auth import GitHubAuthError
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if service is not None:
        app.dependency_overrides[api_v2.get_gate_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_publish_gate_returns_conclusion():
    svc = MagicMock()
    svc.publish.return_value = {"verdict": "no-apto", "conclusion": "failure",
                               "check_run_url": "https://github.com/o/r/runs/1"}
    resp = _client(service=svc).post("/v2/gate/run/r1")
    assert resp.status_code == 200
    assert resp.json()["conclusion"] == "failure"


def test_publish_gate_value_error_is_422():
    svc = MagicMock()
    svc.publish.side_effect = ValueError("run sin veredictos de triaje")
    assert _client(service=svc).post("/v2/gate/run/r1").status_code == 422


def test_publish_gate_github_error_is_502():
    svc = MagicMock()
    svc.publish.side_effect = GitHubError("boom")
    assert _client(service=svc).post("/v2/gate/run/r1").status_code == 502


def test_publish_gate_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/gate/run/r1").status_code == 401


def test_publish_gate_github_auth_error_is_503():
    svc = MagicMock()
    svc.publish.side_effect = GitHubAuthError("no app")
    assert _client(service=svc).post("/v2/gate/run/r1").status_code == 503


def test_publish_gate_db_error_is_502():
    svc = MagicMock()
    svc.publish.side_effect = psycopg.Error()
    assert _client(service=svc).post("/v2/gate/run/r1").status_code == 502
