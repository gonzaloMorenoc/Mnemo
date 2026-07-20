"""Tests for /v2/repo/* endpoints (Task 4 — QA Memory G1 repo ingest)."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.ci.github_app import GitHubError
from src.security import AuthenticatedUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(*, with_user: bool = True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


_GITHUB_CFG_OK = {"configured": True, "repo_full_name": "acme/frontend", "installation_id": "inst-1"}
_GITHUB_CFG_NOT_CONFIGURED = {"configured": False, "repo_full_name": None, "installation_id": None}

_INDEX_RESULT = {"indexed": 5, "by_domain": {"auth": 3, "cart": 2}, "skipped": 1}
_ASSETS = [
    {"id": "a1", "repo_full_name": "acme/frontend", "path": "tests/auth/login.spec.ts",
     "framework": "playwright", "domain": "auth", "created_at": "2026-01-01T00:00:00"},
]


# ---------------------------------------------------------------------------
# POST /v2/repo/index
# ---------------------------------------------------------------------------

def test_repo_index_200():
    """Happy path: GitHub configured → index_repo_tests called → 200 {indexed,...}."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.return_value = _GITHUB_CFG_OK

    mock_host = MagicMock()

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo), \
         patch("src.api_v2._github_codehost_factory", return_value=mock_host), \
         patch("src.api_v2.index_repo_tests", return_value=_INDEX_RESULT) as mock_index, \
         patch("src.api_v2.TestAssetRepository") as mock_repo_cls:

        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 200
    body = r.json()
    assert body["indexed"] == 5
    assert body["by_domain"] == {"auth": 3, "cart": 2}
    assert body["skipped"] == 1
    mock_index.assert_called_once()
    call_kw = mock_index.call_args.kwargs
    assert call_kw["user_id"] == "user-1"
    assert call_kw["org_id"] == "org-1"
    assert call_kw["repo"] == "acme/frontend"


def test_repo_index_401_no_auth():
    """Unauthenticated request → 401."""
    client = make_client(with_user=False)
    r = client.post("/v2/repo/index", json={"org_id": "org-1"})
    assert r.status_code == 401


def test_repo_index_503_not_configured():
    """GitHub not configured → 503."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.return_value = _GITHUB_CFG_NOT_CONFIGURED

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo):
        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 503
    assert "configurado" in r.json()["detail"].lower()


def test_repo_index_503_no_repo_full_name():
    """configured=True but no repo_full_name → 503."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.return_value = {
        "configured": True, "repo_full_name": None, "installation_id": "inst-1"
    }

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo):
        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 503


def test_repo_index_403_non_member_from_get_github_config():
    """get_github_config raises PermissionError (non-member) → 403."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.side_effect = PermissionError("not a member")

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo):
        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 403
    assert "miembro" in r.json()["detail"].lower()


def test_repo_index_403_non_member_from_factory():
    """_github_codehost_factory raises PermissionError → 403."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.return_value = _GITHUB_CFG_OK

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo), \
         patch("src.api_v2._github_codehost_factory", side_effect=PermissionError("not a member")):
        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 403
    assert "miembro" in r.json()["detail"].lower()


def test_repo_index_503_factory_value_error():
    """_github_codehost_factory raises ValueError → 503."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.return_value = _GITHUB_CFG_OK

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo), \
         patch("src.api_v2._github_codehost_factory", side_effect=ValueError("GitHub incompleto")):
        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 503


def test_repo_index_502_github_error():
    """index_repo_tests raises GitHubError → 502."""
    mock_integrations_repo = MagicMock()
    mock_integrations_repo.get_github_config.return_value = _GITHUB_CFG_OK

    mock_host = MagicMock()

    with patch("src.api_v2.get_integrations_repo", return_value=mock_integrations_repo), \
         patch("src.api_v2._github_codehost_factory", return_value=mock_host), \
         patch("src.api_v2.index_repo_tests", side_effect=GitHubError("API rate limit")), \
         patch("src.api_v2.TestAssetRepository"):

        client = make_client()
        r = client.post("/v2/repo/index", json={"org_id": "org-1"})

    assert r.status_code == 502
    assert "API rate limit" in r.json()["detail"]


# ---------------------------------------------------------------------------
# GET /v2/repo/tests
# ---------------------------------------------------------------------------

def test_repo_tests_200():
    """Happy path: list_assets returns rows → 200 list."""
    with patch("src.api_v2.TestAssetRepository") as mock_repo_cls:
        mock_repo_cls.return_value.list_assets.return_value = _ASSETS
        client = make_client()
        r = client.get("/v2/repo/tests", params={"org_id": "org-1"})

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["path"] == "tests/auth/login.spec.ts"
    mock_repo_cls.return_value.list_assets.assert_called_once_with(
        user_id="user-1", org_id="org-1"
    )


def test_repo_tests_200_empty():
    """Empty org (non-member or no assets) → 200 []."""
    with patch("src.api_v2.TestAssetRepository") as mock_repo_cls:
        mock_repo_cls.return_value.list_assets.return_value = []
        client = make_client()
        r = client.get("/v2/repo/tests", params={"org_id": "org-1"})

    assert r.status_code == 200
    assert r.json() == []


def test_repo_tests_401_no_auth():
    """Unauthenticated request → 401."""
    client = make_client(with_user=False)
    r = client.get("/v2/repo/tests", params={"org_id": "org-1"})
    assert r.status_code == 401


def test_repo_tests_422_missing_org_id():
    """Missing org_id query param → 422."""
    client = make_client()
    r = client.get("/v2/repo/tests")
    assert r.status_code == 422
