"""Tests for /v2/onboarding endpoints (Task 2 — QA Memory Onboarding)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SOURCES = [
    {"id": "knowledge:k1", "type": "knowledge", "content": "El flujo de login usa OAuth2."},
    {"id": "defect:d1",    "type": "defect",    "content": "Timeout en sesión SSO con ADFS."},
]

_SUMMARY_RESPONSE = {
    "rules": ["Solo usuarios activos pueden iniciar sesión"],
    "systems": ["auth-service"],
    "existing_tests": ["test_login_happy_path"],
    "historical_bugs": ["Timeout con ADFS"],
    "risks": ["SSO puede fallar"],
    "citations": ["knowledge:k1", "defect:d1"],
}

_PATH_RESPONSE = {
    "days": [
        {"day": 1, "items": ["Leer el flujo feliz"]},
        {"day": 2, "items": ["Casos negativos"]},
        {"day": 3, "items": ["Automatizar un escenario"]},
    ],
    "citations": ["knowledge:k1", "defect:d1"],
}


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _make_repos(sources=None):
    """Return (krepo, arepo) mocks configured so search_unified returns sources."""
    if sources is None:
        sources = _SOURCES
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = sources
    arepo.search_families_semantic.return_value = []
    return krepo, arepo


def make_client(*, krepo=None, arepo=None, with_user: bool = True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    if krepo is not None:
        app.dependency_overrides[api_v2.get_knowledge_repo] = lambda: krepo
    if arepo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: arepo
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /v2/onboarding/domain-summary — happy path
# ---------------------------------------------------------------------------

def test_domain_summary_happy():
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo)

    with patch("src.onboarding.agent.generate_structured", return_value=_SUMMARY_RESPONSE):
        r = client.post("/v2/onboarding/domain-summary", json={"org_id": "org-1", "topic": "autenticación"})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["rules"], list)
    assert isinstance(body["systems"], list)
    assert isinstance(body["existing_tests"], list)
    assert isinstance(body["historical_bugs"], list)
    assert isinstance(body["risks"], list)
    assert isinstance(body["citations"], list)


def test_domain_summary_no_auth_returns_401():
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo, with_user=False)

    r = client.post("/v2/onboarding/domain-summary", json={"org_id": "org-1", "topic": "autenticación"})
    assert r.status_code == 401


def test_domain_summary_topic_too_long_returns_422():
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/onboarding/domain-summary", json={"org_id": "org-1", "topic": "x" * 2001})
    assert r.status_code == 422


def test_domain_summary_non_member_org_returns_empty_fallback():
    """For a foreign org_id, repos return [] → agent returns empty/fallback structure."""
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []
    client = make_client(krepo=krepo, arepo=arepo)

    with patch("src.onboarding.agent.generate_structured", return_value=None):
        r = client.post("/v2/onboarding/domain-summary", json={"org_id": "org-foreign", "topic": "checkout"})

    assert r.status_code == 200
    body = r.json()
    # Fallback structure: all list fields are empty (no sources → no citations leak)
    assert isinstance(body["rules"], list)
    assert isinstance(body["citations"], list)
    # No foreign data leaks: citations must be empty when sources are empty
    assert body["citations"] == []


def test_domain_summary_degrades_without_llm():
    """LLM returning None → fallback structure (all keys present, never raises)."""
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo)

    with patch("src.onboarding.agent.generate_structured", return_value=None):
        r = client.post("/v2/onboarding/domain-summary", json={"org_id": "org-1", "topic": "pagos"})

    assert r.status_code == 200
    body = r.json()
    for key in ("rules", "systems", "existing_tests", "historical_bugs", "risks", "citations"):
        assert key in body
        assert isinstance(body[key], list)


# ---------------------------------------------------------------------------
# POST /v2/onboarding/learning-path — happy path
# ---------------------------------------------------------------------------

def test_learning_path_happy():
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo)

    with patch("src.onboarding.agent.generate_structured", return_value=_PATH_RESPONSE):
        r = client.post("/v2/onboarding/learning-path", json={"org_id": "org-1", "topic": "autenticación"})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["days"], list)
    assert len(body["days"]) == 3
    assert isinstance(body["citations"], list)


def test_learning_path_no_auth_returns_401():
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo, with_user=False)

    r = client.post("/v2/onboarding/learning-path", json={"org_id": "org-1", "topic": "autenticación"})
    assert r.status_code == 401


def test_learning_path_topic_too_long_returns_422():
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/onboarding/learning-path", json={"org_id": "org-1", "topic": "x" * 2001})
    assert r.status_code == 422


def test_learning_path_non_member_org_returns_fallback_no_leak():
    """For a foreign org_id, repos return [] → agent returns fallback, no cross-org data."""
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []
    client = make_client(krepo=krepo, arepo=arepo)

    with patch("src.onboarding.agent.generate_structured", return_value=None):
        r = client.post("/v2/onboarding/learning-path", json={"org_id": "org-foreign", "topic": "checkout"})

    assert r.status_code == 200
    body = r.json()
    # Fallback days is present (at least one item), citations empty (no sources)
    assert isinstance(body["days"], list)
    assert len(body["days"]) >= 1
    assert body["citations"] == []


def test_learning_path_degrades_without_llm():
    """LLM returning None → fallback with one day explaining LLM unavailable."""
    krepo, arepo = _make_repos()
    client = make_client(krepo=krepo, arepo=arepo)

    with patch("src.onboarding.agent.generate_structured", return_value=None):
        r = client.post("/v2/onboarding/learning-path", json={"org_id": "org-1", "topic": "pagos"})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["days"], list)
    assert len(body["days"]) >= 1
    assert isinstance(body["citations"], list)
