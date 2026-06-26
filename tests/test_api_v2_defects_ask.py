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
    """Stub LLM provider that degrades answer_question to fallback mode."""

    pass


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
