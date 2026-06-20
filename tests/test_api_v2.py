from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser
from src.tenant_kb import IngestionResult


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


def _org(role="member"):
    return {"id": "org-1", "name": "Acme QA", "join_code": "ABC123", "role": role, "created_at": "2026-06-19T10:00:00"}


def test_list_orgs_maps_response():
    repo = MagicMock()
    repo.list_user_organizations.return_value = [_org("owner")]
    client = make_client(repo=repo)
    resp = client.get("/v2/orgs")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "org-1"
    assert body[0]["role"] == "owner"


def test_create_org_validation_error():
    repo = MagicMock()
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "x"})  # min_length=2
    assert resp.status_code == 422


def test_create_org_happy_path():
    repo = MagicMock()
    repo.create_organization.return_value = _org("owner")
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "Acme QA"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme QA"


def test_join_org_unknown_code_returns_404():
    repo = MagicMock()
    repo.join_organization.side_effect = ValueError("Could not join organization with the provided code")
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs/join", json={"join_code": "BADCODE"})
    assert resp.status_code == 404


def test_upload_happy_path():
    repo = MagicMock()
    repo.ingest_file.return_value = IngestionResult(
        document_id="doc-1", chunk_count=3, global_document_id=None, storage_path="/uploads/user-123/a.log"
    )
    client = make_client(repo=repo)
    resp = client.post(
        "/v2/upload",
        data={"scope": "user", "contribute_global": "false"},
        files={"file": ("a.log", b"NullPointerException at Foo.java:42", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc-1"
    assert body["chunk_count"] == 3
    kwargs = repo.ingest_file.call_args.kwargs
    assert kwargs["scope"] == "user"
    assert kwargs["filename"] == "a.log"
    assert kwargs["data"] == b"NullPointerException at Foo.java:42"


def test_upload_org_scope_without_org_id_is_400():
    repo = MagicMock()
    repo.ingest_file.side_effect = ValueError("org_id is required when scope is 'org'")
    client = make_client(repo=repo)
    resp = client.post(
        "/v2/upload",
        data={"scope": "org", "contribute_global": "false"},
        files={"file": ("a.log", b"some error log content", "text/plain")},
    )
    assert resp.status_code == 400


def test_health_reports_multi_tenant_flag(monkeypatch):
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: True)
    client = make_client(with_user=False)  # /v2/health requires no auth
    resp = client.get("/v2/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["multi_tenant_enabled"] is True
    assert "status" in body
