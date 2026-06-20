import psycopg
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(*, repo=None, narrator=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if narrator is not None:
        app.dependency_overrides[api_v2.get_narrator] = lambda: narrator
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_assurance_verdict_happy():
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {
        "run": {"id": "r1", "project": "proj-a", "source": "allure"},
        "summary": {"ingested": 3, "known": 1, "novel": 2},
        "families": [{"id": "f1", "title": "Timeout", "occurrence_count": 5, "run_count": 1}],
    }
    narrator = MagicMock()
    narrator.summarize.return_value = "Resumen del run."
    client = make_client(repo=repo, narrator=narrator)
    resp = client.get("/v2/assurance/run/r1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r1" and body["known"] == 1 and body["novel"] == 2
    assert body["risk"] == "atencion"
    assert body["top_families"][0]["id"] == "f1" and body["top_families"][0]["recurring"] is True
    assert body["narrative"] == "Resumen del run."


def test_assurance_verdict_not_found_is_404():
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {"run": None, "summary": {}, "families": []}
    client = make_client(repo=repo, narrator=MagicMock())
    resp = client.get("/v2/assurance/run/missing")
    assert resp.status_code == 404


def test_assurance_verdict_requires_auth():
    client = make_client(repo=MagicMock(), narrator=MagicMock(), with_user=False)
    resp = client.get("/v2/assurance/run/r1")
    assert resp.status_code == 401


def test_assurance_verdict_narrator_failure_degrades_gracefully():
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {
        "run": {"id": "r1", "project": "p", "source": "allure"},
        "summary": {"ingested": 1, "known": 0, "novel": 1},
        "families": [{"id": "f1", "title": "T", "occurrence_count": 1, "run_count": 1}],
    }
    narrator = MagicMock()
    narrator.summarize.side_effect = RuntimeError("ollama down")
    client = make_client(repo=repo, narrator=narrator)
    resp = client.get("/v2/assurance/run/r1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["narrative"] is None
    assert body["novel"] == 1 and body["risk"] == "atencion"


def test_assurance_verdict_db_error_is_502():
    repo = MagicMock()
    repo.get_run_assurance_data.side_effect = psycopg.OperationalError("db down")
    client = make_client(repo=repo, narrator=MagicMock())
    resp = client.get("/v2/assurance/run/r1")
    assert resp.status_code == 502
