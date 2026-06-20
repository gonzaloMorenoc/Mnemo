from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-123", email="t@example.com", claims={})


def make_client(*, repo=None, analyzer=None, with_user=True) -> TestClient:
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_repo] = lambda: repo
    if analyzer is not None:
        app.dependency_overrides[api_v2.get_analyzer] = lambda: analyzer
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _fake_user
    return TestClient(app)


def _ctx(scope, title, sim):
    return {
        "chunk_id": "c1", "document_id": "d1", "scope": scope,
        "owner_user_id": None, "org_id": None,
        "source_title": title, "content": "boom", "similarity": sim,
    }


def test_analyze_requires_auth():
    client = make_client(repo=MagicMock(), analyzer=MagicMock(), with_user=False)
    resp = client.post("/v2/analyze", json={"error_log": "TimeoutException at line 10"})
    assert resp.status_code == 401


def test_analyze_happy_path_maps_response():
    repo = MagicMock()
    repo.retrieve_context.return_value = [_ctx("org", "ticket-1", 0.9), _ctx("global", "kb-doc", 0.7)]
    repo.save_analysis.return_value = 42
    analyzer = MagicMock()
    analyzer.analyze.return_value = {
        "root_cause": "rc", "why_it_happened": "why", "how_to_fix": "fix",
        "suggested_patch_steps": ["s1"], "confidence": 0.8,
    }
    client = make_client(repo=repo, analyzer=analyzer)
    resp = client.post("/v2/analyze", json={"error_log": "TimeoutException at line 10", "org_id": "org-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis"]["root_cause"] == "rc"
    assert body["source_scopes"] == ["org", "global"]
    assert len(body["sources"]) == 2
    assert body["sources"][0] == {"scope": "org", "source_title": "ticket-1", "similarity": 0.9}
    assert body["analysis_id"] == 42


def test_analyze_empty_contexts_returns_fallback():
    repo = MagicMock()
    repo.retrieve_context.return_value = []
    repo.save_analysis.return_value = 7
    analyzer = MagicMock()
    analyzer.analyze.return_value = {
        "root_cause": "Insufficient context", "why_it_happened": "x", "how_to_fix": "y",
        "suggested_patch_steps": [], "confidence": 0.2,
    }
    client = make_client(repo=repo, analyzer=analyzer)
    resp = client.post("/v2/analyze", json={"error_log": "weird error here"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == []
    assert body["source_scopes"] == []


def test_analyze_503_when_not_configured(monkeypatch):
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: False)
    client = make_client(analyzer=MagicMock())
    resp = client.post("/v2/analyze", json={"error_log": "TimeoutException at line 10"})
    assert resp.status_code == 503
