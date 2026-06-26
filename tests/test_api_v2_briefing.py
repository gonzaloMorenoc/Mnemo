"""Tests for GET /v2/runs/{run_id}/briefing.

Dependency-override pattern mirrors tests/test_api_v2_defects_ask.py.
All three key invariants are tested:
- verdict comes from the certificate, NOT the LLM
- 404 when the run doesn't exist (get_run_assurance_data → run: None)
- "sin certificar" when get_certificate returns None
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _run_data():
    return {"run": {"id": "r1", "project": "my-svc", "source": "ci"},
            "summary": {"ingested": 5, "known": 3, "novel": 2},
            "families": []}


class _FakeProvider:
    """Stub LLM provider: returns a fixed briefing JSON without loading any model."""

    def complete(self, prompt: str) -> str:
        return (
            '{"summary":"s","verdict_line":"v","highlights":["h1"],'
            '"recommendation":"r","citations":["cert"]}'
        )


@pytest.fixture
def client_and_mocks():
    """Build a TestClient with mocked repos; returns (client, namespace(assurance, cert, actions))."""
    assurance_repo = MagicMock()
    cert_repo = MagicMock()
    actions_repo = MagicMock()

    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: assurance_repo
    app.dependency_overrides[api_v2.get_certificate_repo] = lambda: cert_repo
    app.dependency_overrides[api_v2.get_action_repo] = lambda: actions_repo
    # Stub LLM provider so no model is loaded; endpoint still degrades gracefully anyway
    app.dependency_overrides[api_v2.get_llm_provider] = lambda: _FakeProvider()

    client = TestClient(app)
    mocks = SimpleNamespace(assurance=assurance_repo, cert=cert_repo, actions=actions_repo)
    return client, mocks


def test_briefing_verdict_comes_from_certificate_not_llm(client_and_mocks):
    client, mocks = client_and_mocks
    mocks.assurance.get_run_assurance_data.return_value = _run_data()
    mocks.cert.get_certificate.return_value = {"verdict": "apto", "risk_score": 0.1, "canonical_json": "{}"}
    mocks.actions.list_actions_for_run.return_value = []
    r = client.get("/v2/runs/r1/briefing")
    assert r.status_code == 200
    assert r.json()["verdict"] == "apto"   # from the certificate, NOT the LLM


def test_briefing_404_when_run_missing(client_and_mocks):
    client, mocks = client_and_mocks
    mocks.assurance.get_run_assurance_data.return_value = {"run": None, "summary": {}, "families": []}
    assert client.get("/v2/runs/none/briefing").status_code == 404


def test_briefing_sin_certificar_when_no_cert(client_and_mocks):
    client, mocks = client_and_mocks
    mocks.assurance.get_run_assurance_data.return_value = _run_data()
    mocks.cert.get_certificate.return_value = None
    mocks.actions.list_actions_for_run.return_value = []
    r = client.get("/v2/runs/r1/briefing")
    assert r.status_code == 200
    assert r.json()["verdict"] == "sin certificar"


def test_briefing_response_schema(client_and_mocks):
    """Response contains all expected fields."""
    client, mocks = client_and_mocks
    mocks.assurance.get_run_assurance_data.return_value = _run_data()
    mocks.cert.get_certificate.return_value = {"verdict": "no-apto", "risk_score": 5, "canonical_json": "{}"}
    mocks.actions.list_actions_for_run.return_value = [
        {"id": "a1", "kind": "ticket", "summary": "Fix checkout", "triage_verdict_id": "tv1",
         "run_id": "r1", "org_id": "o1", "payload": {}, "status": "proposed",
         "artifact_ref": None, "approved_by": None, "approved_at": None, "reject_reason": None}
    ]
    r = client.get("/v2/runs/r1/briefing")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"verdict", "summary", "recommendation", "highlights", "citations"}
    assert isinstance(body["highlights"], list)
    assert isinstance(body["citations"], list)
    assert body["verdict"] == "no-apto"


def test_briefing_degrades_when_llm_down(client_and_mocks):
    """When LLM is unavailable the endpoint still returns 200 (degraded mode)."""
    client, mocks = client_and_mocks
    mocks.assurance.get_run_assurance_data.return_value = _run_data()
    mocks.cert.get_certificate.return_value = {"verdict": "apto", "risk_score": 0, "canonical_json": "{}"}
    mocks.actions.list_actions_for_run.return_value = []

    # Override get_llm_provider to raise, forcing the endpoint to degrade
    client.app.dependency_overrides[api_v2.get_llm_provider] = lambda: (_ for _ in ()).throw(
        RuntimeError("LLM unavailable"))

    r = client.get("/v2/runs/r1/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "apto"
    assert isinstance(body["summary"], str) and len(body["summary"]) > 0
