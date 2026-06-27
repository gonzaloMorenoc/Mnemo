from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


class _StubEmbedder:
    """Stub embedder that returns a zero vector without loading HuggingFace."""

    def embed(self, text: str):
        return [0.0] * 384


class _StubProvider:
    """Stub LLM provider that raises on complete() to simulate LLM down."""

    def complete(self, prompt):
        raise RuntimeError("LLM unavailable")


@pytest.fixture
def client_and_mocks():
    repo = MagicMock()
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    app.dependency_overrides[api_v2.get_embedder] = lambda: _StubEmbedder()
    client = TestClient(app)
    return client, repo


def test_ask_returns_answer_and_citations(client_and_mocks):
    client, repo = client_and_mocks
    repo.search_families_semantic.return_value = [
        {"family_id": "fam1", "title": "checkout 500", "label": "real",
         "occurrence_count": 3, "root_cause": "500"}]
    r = client.post("/v2/defects/ask", json={"org_id": "o1", "question": "¿qué rompe checkout?"})
    assert r.status_code == 200
    body = r.json()
    assert "families" in body and body["families"][0]["family_id"] == "fam1"
    assert isinstance(body["citations"], list) and isinstance(body["answer"], str)


def test_ask_empty_when_no_families(client_and_mocks):
    client, repo = client_and_mocks
    repo.search_families_semantic.return_value = []
    r = client.post("/v2/defects/ask", json={"org_id": "o1", "question": "¿algo?"})
    assert r.status_code == 200 and r.json()["families"] == []


def test_ask_degrades_when_llm_down(client_and_mocks):
    """When LLM provider is down, endpoint returns 200 with families and degraded answer."""
    client, repo = client_and_mocks
    repo.search_families_semantic.return_value = [
        {"family_id": "fam1", "title": "checkout 500", "label": "real",
         "occurrence_count": 3, "root_cause": "500"},
        {"family_id": "fam2", "title": "login timeout", "label": "flaky",
         "occurrence_count": 1, "root_cause": None}
    ]
    # Override get_llm_provider to raise an exception
    import src.api_v2 as api_v2
    client.app.dependency_overrides[api_v2.get_llm_provider] = lambda: _StubProvider()

    r = client.post("/v2/defects/ask", json={"org_id": "o1", "question": "¿qué rompe checkout?"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["families"]) == 2
    assert "checkout 500" in body["answer"]  # degraded fallback mentions family title
    assert body["citations"] == ["fam1", "fam2"]  # cites the found families

    # Clean up override
    del client.app.dependency_overrides[api_v2.get_llm_provider]


def test_ask_rejects_overlong_question(client_and_mocks):
    client, _ = client_and_mocks
    r = client.post("/v2/defects/ask", json={"org_id": "o1", "question": "x" * 5000})
    assert r.status_code == 422   # Pydantic rechaza > max_length antes de tocar el repo
