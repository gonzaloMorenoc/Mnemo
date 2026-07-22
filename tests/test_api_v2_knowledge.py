"""Tests for /v2/knowledge endpoints (Task 4 — QA Memory Fase 1a)."""
import psycopg
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _make_item(**kw):
    base = {
        "id": "item-1",
        "kind": "leccion",
        "title": "Título de prueba",
        "domain": None,
        "tags": [],
        "confidence": "confirmado",
        "created_at": "2026-06-27T00:00:00",
    }
    base.update(kw)
    return base


def make_client(
    *,
    krepo=None,
    arepo=None,
    with_user: bool = True,
):
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
# POST /v2/knowledge — create
# ---------------------------------------------------------------------------

def test_create_knowledge_happy():
    krepo = MagicMock()
    krepo.create_item.return_value = _make_item()
    client = make_client(krepo=krepo)

    r = client.post("/v2/knowledge", json={
        "org_id": "org-1", "kind": "leccion", "title": "Título de prueba",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "item-1"
    assert body["kind"] == "leccion"
    krepo.create_item.assert_called_once()


def test_create_knowledge_invalid_kind_returns_400():
    krepo = MagicMock()
    krepo.create_item.side_effect = ValueError("kind inválido: badkind")
    client = make_client(krepo=krepo)

    r = client.post("/v2/knowledge", json={
        "org_id": "org-1", "kind": "badkind", "title": "T",
    })
    assert r.status_code == 400
    assert "kind inválido" in r.json()["detail"]


def test_create_knowledge_not_member_returns_403():
    krepo = MagicMock()
    krepo.create_item.return_value = None  # membership check failed
    client = make_client(krepo=krepo)

    r = client.post("/v2/knowledge", json={
        "org_id": "org-foreign", "kind": "leccion", "title": "T",
    })
    assert r.status_code == 403


def test_create_knowledge_no_auth_returns_401():
    krepo = MagicMock()
    client = make_client(krepo=krepo, with_user=False)

    r = client.post("/v2/knowledge", json={
        "org_id": "org-1", "kind": "leccion", "title": "T",
    })
    assert r.status_code == 401


def test_create_knowledge_db_error_returns_502():
    krepo = MagicMock()
    krepo.create_item.side_effect = psycopg.OperationalError("db down")
    client = make_client(krepo=krepo)

    r = client.post("/v2/knowledge", json={
        "org_id": "org-1", "kind": "leccion", "title": "T",
    })
    assert r.status_code == 502


def test_create_knowledge_title_too_long_returns_422():
    krepo = MagicMock()
    client = make_client(krepo=krepo)

    r = client.post("/v2/knowledge", json={
        "org_id": "org-1", "kind": "leccion", "title": "x" * 301,
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /v2/knowledge — list
# ---------------------------------------------------------------------------

def test_list_knowledge_happy():
    krepo = MagicMock()
    krepo.list_items.return_value = [_make_item(), _make_item(id="item-2", title="Segundo")]
    client = make_client(krepo=krepo)

    r = client.get("/v2/knowledge?org_id=org-1")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_knowledge_no_auth_returns_401():
    krepo = MagicMock()
    client = make_client(krepo=krepo, with_user=False)

    r = client.get("/v2/knowledge?org_id=org-1")
    assert r.status_code == 401


def test_list_knowledge_isolation_foreign_org_returns_empty():
    """Repo returns [] for a foreign org_id — endpoint must relay that empty list."""
    krepo = MagicMock()
    krepo.list_items.return_value = []
    client = make_client(krepo=krepo)

    r = client.get("/v2/knowledge?org_id=org-foreign")
    assert r.status_code == 200
    assert r.json() == []
    krepo.list_items.assert_called_once_with(
        user_id="user-1", org_id="org-foreign", kind=None, domain=None,
        project=None, status=None,
    )


def test_list_knowledge_with_filters():
    krepo = MagicMock()
    krepo.list_items.return_value = [_make_item(kind="flujo", domain="checkout")]
    client = make_client(krepo=krepo)

    r = client.get("/v2/knowledge?org_id=org-1&kind=flujo&domain=checkout")
    assert r.status_code == 200
    krepo.list_items.assert_called_once_with(
        user_id="user-1", org_id="org-1", kind="flujo", domain="checkout",
        project=None, status=None,
    )


# ---------------------------------------------------------------------------
# GET /v2/knowledge/{item_id} — get
# ---------------------------------------------------------------------------

def test_get_knowledge_happy():
    krepo = MagicMock()
    krepo.get_item.return_value = _make_item()
    client = make_client(krepo=krepo)

    r = client.get("/v2/knowledge/item-1?org_id=org-1")
    assert r.status_code == 200
    assert r.json()["id"] == "item-1"


def test_get_knowledge_missing_returns_404():
    krepo = MagicMock()
    krepo.get_item.return_value = None
    client = make_client(krepo=krepo)

    r = client.get("/v2/knowledge/does-not-exist?org_id=org-1")
    assert r.status_code == 404


def test_get_knowledge_no_auth_returns_401():
    krepo = MagicMock()
    client = make_client(krepo=krepo, with_user=False)

    r = client.get("/v2/knowledge/item-1?org_id=org-1")
    assert r.status_code == 401


def test_get_knowledge_isolation_foreign_org_returns_404():
    """Repo returns None for item in foreign org — must be 404, not leaking data."""
    krepo = MagicMock()
    krepo.get_item.return_value = None
    client = make_client(krepo=krepo)

    r = client.get("/v2/knowledge/item-1?org_id=org-foreign")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /v2/knowledge/search
# ---------------------------------------------------------------------------

def test_search_knowledge_happy():
    krepo = MagicMock()
    arepo = MagicMock()
    # KnowledgeService.search_unified is built from the real service but with mocked repos
    krepo.search_semantic.return_value = [
        {"id": "k1", "title": "Leccion checkout", "challenge": "Fallo", "approach": "Fix",
         "outcome": None, "confidence": "confirmado"},
    ]
    arepo.search_families_semantic.return_value = []
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/search", json={
        "org_id": "org-1", "query": "checkout error", "k": 5,
    })
    assert r.status_code == 200
    results = r.json()
    assert len(results) >= 1
    assert results[0]["type"] == "knowledge"


def test_search_knowledge_no_auth_returns_401():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo, with_user=False)

    r = client.post("/v2/knowledge/search", json={"org_id": "org-1", "query": "q"})
    assert r.status_code == 401


def test_search_knowledge_query_too_long_returns_422():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/search", json={"org_id": "org-1", "query": "x" * 2001})
    assert r.status_code == 422


def test_search_knowledge_isolation_foreign_org_empty():
    """For a foreign org_id, both repos return [] → search returns empty list."""
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/search", json={"org_id": "org-foreign", "query": "q"})
    assert r.status_code == 200
    assert r.json() == []


def test_search_knowledge_k_too_large_returns_422():
    """M1: k > 100 must be rejected with 422 (cota de seguridad)."""
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/search", json={"org_id": "org-1", "query": "q", "k": 1000})
    assert r.status_code == 422


def test_search_knowledge_k_zero_returns_422():
    """M1: k < 1 must be rejected with 422."""
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/search", json={"org_id": "org-1", "query": "q", "k": 0})
    assert r.status_code == 422


def test_search_knowledge_k_boundary_100_accepted():
    """M1: k = 100 (boundary) must be accepted."""
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/search", json={"org_id": "org-1", "query": "q", "k": 100})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /v2/knowledge/ask
# ---------------------------------------------------------------------------

def test_ask_knowledge_happy():
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = [
        {"id": "k1", "title": "Regla pago", "challenge": "timeout", "approach": "retry",
         "outcome": None, "confidence": "confirmado"},
    ]
    arepo.search_families_semantic.return_value = []
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/ask", json={
        "org_id": "org-1", "question": "¿qué hacer con timeouts?",
    })
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body
    assert "citations" in body


def test_ask_knowledge_no_auth_returns_401():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo, with_user=False)

    r = client.post("/v2/knowledge/ask", json={"org_id": "org-1", "question": "q"})
    assert r.status_code == 401


def test_ask_knowledge_question_too_long_returns_422():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo)

    r = client.post("/v2/knowledge/ask", json={"org_id": "org-1", "question": "x" * 2001})
    assert r.status_code == 422


def test_ask_knowledge_llm_down_degrades_gracefully():
    """When the LLM is unavailable, ask returns 200 with a fallback answer (no exception)."""
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = [
        {"id": "k1", "title": "Regla pago", "challenge": "timeout", "approach": "retry",
         "outcome": None, "confidence": "confirmado"},
    ]
    arepo.search_families_semantic.return_value = []

    # Patch answer_over_sources inside nl_query to simulate LLM-down fallback
    import src.ai.nl_query as nl_query_mod
    original = nl_query_mod.generate_structured

    def _fail(*a, **kw):
        return None  # simulate LLM returning nothing

    nl_query_mod.generate_structured = _fail
    try:
        client = make_client(krepo=krepo, arepo=arepo)
        r = client.post("/v2/knowledge/ask", json={
            "org_id": "org-1", "question": "¿qué hacer con timeouts?",
        })
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["answer"], str) and len(body["answer"]) > 0
        assert isinstance(body["citations"], list)
    finally:
        nl_query_mod.generate_structured = original
