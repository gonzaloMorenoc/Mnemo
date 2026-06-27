"""Tests for /v2/automation endpoints (Task 3 — QA Continuity Automation)."""
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


# ---------------------------------------------------------------------------
# POST /v2/automation/generate
# ---------------------------------------------------------------------------

def test_generate_200():
    """Valid case returns {code, filename, notes} (fallback path — no LLM needed)."""
    case = {"title": "Login exitoso", "steps": ["Ir a /login", "Enviar credenciales"], "expected": "Dashboard"}
    client = make_client()
    r = client.post("/v2/automation/generate", json={"case": case})
    assert r.status_code == 200
    body = r.json()
    assert "code" in body
    assert "filename" in body
    assert "notes" in body
    assert body["code"]
    assert body["filename"].endswith(".spec.ts")


def test_generate_200_with_style_sample():
    """style_sample is forwarded to generate_playwright_test."""
    case = {"title": "Logout", "steps": ["Click logout"], "expected": "Landing"}
    style = "import { test, expect } from '@playwright/test';"

    with patch("src.api_v2.generate_playwright_test", return_value={"code": "x", "filename": "a.spec.ts", "notes": ""}) as mock_gen:
        client = make_client()
        r = client.post("/v2/automation/generate", json={"case": case, "style_sample": style})

    assert r.status_code == 200
    mock_gen.assert_called_once_with(case=case, style_sample=style)


def test_generate_401_no_auth():
    """Unauthenticated request → 401."""
    case = {"title": "Caso", "steps": [], "expected": "OK"}
    client = make_client(with_user=False)
    r = client.post("/v2/automation/generate", json={"case": case})
    assert r.status_code == 401


def test_generate_400_empty_case():
    """Empty dict case → 400."""
    client = make_client()
    r = client.post("/v2/automation/generate", json={"case": {}})
    assert r.status_code == 400
    assert "case" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /v2/automation/pr
# ---------------------------------------------------------------------------

def _pr_payload(**kw):
    base = {
        "org_id": "org-1",
        "code": "import { test } from '@playwright/test';",
        "filename": "login.spec.ts",
    }
    base.update(kw)
    return base


def test_pr_200():
    """Stubbed factory + host → returns {pr_url}."""
    mock_host = MagicMock()
    mock_host.open_pr_with_new_file.return_value = "https://github.com/acme/repo/pull/42"

    with patch("src.api_v2._github_codehost_factory", return_value=mock_host):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload())

    assert r.status_code == 200
    assert r.json() == {"pr_url": "https://github.com/acme/repo/pull/42"}
    mock_host.open_pr_with_new_file.assert_called_once()
    call_kw = mock_host.open_pr_with_new_file.call_args.kwargs
    assert call_kw["file_path"] == "tests/login.spec.ts"
    assert call_kw["marker"] == "automation:login.spec.ts"


def test_pr_200_custom_title():
    """Custom title is forwarded."""
    mock_host = MagicMock()
    mock_host.open_pr_with_new_file.return_value = "https://github.com/acme/repo/pull/43"

    with patch("src.api_v2._github_codehost_factory", return_value=mock_host):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload(title="mi PR"))

    assert r.status_code == 200
    call_kw = mock_host.open_pr_with_new_file.call_args.kwargs
    assert call_kw["title"] == "mi PR"


def test_pr_200_default_title():
    """No title → default title built from filename."""
    mock_host = MagicMock()
    mock_host.open_pr_with_new_file.return_value = "https://github.com/acme/repo/pull/44"

    with patch("src.api_v2._github_codehost_factory", return_value=mock_host):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload())

    call_kw = mock_host.open_pr_with_new_file.call_args.kwargs
    assert call_kw["title"] == "test(automation): login.spec.ts"


def test_pr_401_no_auth():
    """Unauthenticated request → 401."""
    client = make_client(with_user=False)
    r = client.post("/v2/automation/pr", json=_pr_payload())
    assert r.status_code == 401


def test_pr_403_non_member():
    """_github_codehost_factory raises PermissionError → 403."""
    with patch("src.api_v2._github_codehost_factory", side_effect=PermissionError("not a member")):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload(org_id="foreign-org"))

    assert r.status_code == 403
    assert "miembro" in r.json()["detail"].lower()


def test_pr_503_not_configured():
    """_github_codehost_factory raises ValueError (GitHub not configured) → 503."""
    with patch("src.api_v2._github_codehost_factory", side_effect=ValueError("GitHub no configurado para el org")):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload())

    assert r.status_code == 503
    assert "configurado" in r.json()["detail"].lower()


def test_pr_502_github_error():
    """open_pr_with_new_file raises GitHubError → 502."""
    mock_host = MagicMock()
    mock_host.open_pr_with_new_file.side_effect = GitHubError("API error")

    with patch("src.api_v2._github_codehost_factory", return_value=mock_host):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload())

    assert r.status_code == 502


def test_pr_502_falsy_url():
    """open_pr_with_new_file returns falsy (None/empty) → 502."""
    mock_host = MagicMock()
    mock_host.open_pr_with_new_file.return_value = None

    with patch("src.api_v2._github_codehost_factory", return_value=mock_host):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload())

    assert r.status_code == 502
    assert "PR" in r.json()["detail"]


def test_pr_422_path_traversal_filename():
    """Path traversal filenames are rejected at model validation → 422 (never reach GitHub)."""
    client = make_client()

    # Classic path traversal — escapes tests/ directory
    r = client.post("/v2/automation/pr", json=_pr_payload(filename="../../app.py"))
    assert r.status_code == 422

    # Traversal disguised as .spec.ts
    r = client.post("/v2/automation/pr", json=_pr_payload(filename="../evil.spec.ts"))
    assert r.status_code == 422

    # Plain directory separator — also blocked
    r = client.post("/v2/automation/pr", json=_pr_payload(filename="subdir/evil.spec.ts"))
    assert r.status_code == 422


def test_pr_200_valid_spects_filename():
    """A valid .spec.ts filename passes the pattern and reaches GitHub."""
    mock_host = MagicMock()
    mock_host.open_pr_with_new_file.return_value = "https://github.com/acme/repo/pull/99"

    with patch("src.api_v2._github_codehost_factory", return_value=mock_host):
        client = make_client()
        r = client.post("/v2/automation/pr", json=_pr_payload(filename="login.spec.ts"))

    assert r.status_code == 200
    assert r.json()["pr_url"] == "https://github.com/acme/repo/pull/99"
