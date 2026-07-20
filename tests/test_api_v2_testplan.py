"""Tests for /v2/test-plan endpoints (Task 5 — QA Memory Fase 1b)."""
import io
from unittest.mock import MagicMock, patch

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


def _make_plan(**kw):
    base = {
        "summary": "Plan de pruebas de ejemplo",
        "systems": [],
        "risks": [],
        "preconditions": [],
        "test_data": [],
        "cases": [{"title": "Caso 1", "steps": ["Paso 1"], "expected": "OK"}],
        "gaps": [],
        "open_questions": [],
        "citations": ["src-1"],
    }
    base.update(kw)
    return base


def make_client(
    *,
    krepo=None,
    arepo=None,
    integrations=None,
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
    if integrations is not None:
        app.dependency_overrides[api_v2.get_integrations_repo] = lambda: integrations
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /v2/test-plan/generate — hu_text
# ---------------------------------------------------------------------------

def test_generate_with_hu_text_200():
    plan = _make_plan()
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []

    with patch("src.api_v2.generate_test_plan", return_value=plan) as mock_gen:
        client = make_client(krepo=krepo, arepo=arepo, integrations=MagicMock())
        r = client.post(
            "/v2/test-plan/generate",
            data={"org_id": "org-1", "hu_text": "Como usuario quiero X para Y"},
        )

    assert r.status_code == 200
    body = r.json()
    assert "plan" in body
    assert "citations" in body
    assert body["citations"] == ["src-1"]
    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["org_id"] == "org-1"
    assert call_kwargs["hu_text"] == "Como usuario quiero X para Y"


def test_generate_with_jira_url_200():
    plan = _make_plan()
    krepo = MagicMock()
    arepo = MagicMock()
    integrations = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []

    with patch("src.api_v2.hu_text_from_jira", return_value="HU desde Jira") as mock_jira, \
         patch("src.api_v2.generate_test_plan", return_value=plan):
        client = make_client(krepo=krepo, arepo=arepo, integrations=integrations)
        r = client.post(
            "/v2/test-plan/generate",
            data={
                "org_id": "org-1",
                "jira_url": "https://acme.atlassian.net/browse/DIA-1",
            },
        )

    assert r.status_code == 200
    mock_jira.assert_called_once_with(
        url="https://acme.atlassian.net/browse/DIA-1",
        org_id="org-1",
        user_id="user-1",
        repo=integrations,
    )


def test_generate_with_file_200():
    plan = _make_plan()
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []
    file_bytes = b"Historia de usuario: como QA quiero probar el login"

    with patch("src.api_v2.resolve_hu_from_upload", return_value="HU desde archivo") as mock_ingest, \
         patch("src.api_v2.generate_test_plan", return_value=plan):
        client = make_client(krepo=krepo, arepo=arepo, integrations=MagicMock())
        r = client.post(
            "/v2/test-plan/generate",
            data={"org_id": "org-1"},
            files={"file": ("story.txt", file_bytes, "text/plain")},
        )

    assert r.status_code == 200
    mock_ingest.assert_called_once_with("story.txt", file_bytes)


def test_generate_case_format_gherkin():
    plan = _make_plan()
    krepo = MagicMock()
    arepo = MagicMock()
    krepo.search_semantic.return_value = []
    arepo.search_families_semantic.return_value = []

    with patch("src.api_v2.generate_test_plan", return_value=plan) as mock_gen:
        client = make_client(krepo=krepo, arepo=arepo, integrations=MagicMock())
        r = client.post(
            "/v2/test-plan/generate",
            data={
                "org_id": "org-1",
                "hu_text": "Historia",
                "case_format": "gherkin",
            },
        )

    assert r.status_code == 200
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs["case_format"] == "gherkin"


def test_generate_no_auth_401():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo, with_user=False)

    r = client.post(
        "/v2/test-plan/generate",
        data={"org_id": "org-1", "hu_text": "Historia"},
    )
    assert r.status_code == 401


def test_generate_non_member_403():
    krepo = MagicMock()
    arepo = MagicMock()
    integrations = MagicMock()

    with patch("src.api_v2.hu_text_from_jira", side_effect=PermissionError("not a member")):
        client = make_client(krepo=krepo, arepo=arepo, integrations=integrations)
        r = client.post(
            "/v2/test-plan/generate",
            data={
                "org_id": "org-foreign",
                "jira_url": "https://acme.atlassian.net/browse/DIA-1",
            },
        )

    assert r.status_code == 403


def test_generate_empty_hu_400():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo, integrations=MagicMock())

    r = client.post(
        "/v2/test-plan/generate",
        data={"org_id": "org-1", "hu_text": "   "},
    )
    assert r.status_code == 400
    assert "vacía" in r.json()["detail"]


def test_generate_no_source_400():
    krepo = MagicMock()
    arepo = MagicMock()
    client = make_client(krepo=krepo, arepo=arepo, integrations=MagicMock())

    r = client.post(
        "/v2/test-plan/generate",
        data={"org_id": "org-1"},
    )
    assert r.status_code == 400
    assert "No se proporcionó HU" in r.json()["detail"]


def test_generate_unsupported_file_400():
    krepo = MagicMock()
    arepo = MagicMock()

    with patch("src.api_v2.resolve_hu_from_upload", side_effect=ValueError("extensión no soportada: '.xls'")):
        client = make_client(krepo=krepo, arepo=arepo, integrations=MagicMock())
        r = client.post(
            "/v2/test-plan/generate",
            data={"org_id": "org-1"},
            files={"file": ("story.xls", b"data", "application/vnd.ms-excel")},
        )

    assert r.status_code == 400
    assert "extensión no soportada" in r.json()["detail"]


# ---------------------------------------------------------------------------
# POST /v2/test-plan/export/xray
# ---------------------------------------------------------------------------

def _xray_creds():
    return {
        "base_url": "https://xray.cloud.getxray.app",
        "client_id": "id-123",
        "client_secret": "secret-abc",
        "mode": "cloud",
    }


def test_export_xray_200():
    plan = _make_plan()

    with patch("src.api_v2.XrayConfig") as MockConfig, \
         patch("src.api_v2.XrayClient") as MockClient:
        mock_cfg_instance = MockConfig.return_value
        mock_cfg_instance.get.return_value = _xray_creds()
        mock_client_instance = MockClient.return_value
        mock_client_instance.import_plan.return_value = ["ACME-1", "ACME-2"]

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-1", "plan": plan, "case_format": "manual"},
        )

    assert r.status_code == 200
    body = r.json()
    assert body["keys"] == ["ACME-1", "ACME-2"]


def test_export_xray_503_not_configured():
    """XrayConfig.get returns None → 503."""
    plan = _make_plan()

    with patch("src.api_v2.XrayConfig") as MockConfig:
        mock_cfg_instance = MockConfig.return_value
        mock_cfg_instance.get.return_value = None

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-1", "plan": plan, "case_format": "manual"},
        )

    assert r.status_code == 503
    assert "Xray no configurado" in r.json()["detail"]


def test_export_xray_503_xray_not_configured_exc():
    """XrayNotConfigured raised by client → 503."""
    from src.xray.client import XrayNotConfigured
    plan = _make_plan()

    with patch("src.api_v2.XrayConfig") as MockConfig, \
         patch("src.api_v2.XrayClient") as MockClient:
        mock_cfg_instance = MockConfig.return_value
        mock_cfg_instance.get.return_value = _xray_creds()
        mock_client_instance = MockClient.return_value
        mock_client_instance.import_plan.side_effect = XrayNotConfigured("not configured")

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-1", "plan": plan, "case_format": "manual"},
        )

    assert r.status_code == 503


def test_export_xray_502_import_error():
    """XrayImportError from client → 502."""
    from src.xray.client import XrayImportError
    plan = _make_plan()

    with patch("src.api_v2.XrayConfig") as MockConfig, \
         patch("src.api_v2.XrayClient") as MockClient:
        mock_cfg_instance = MockConfig.return_value
        mock_cfg_instance.get.return_value = _xray_creds()
        mock_client_instance = MockClient.return_value
        mock_client_instance.import_plan.side_effect = XrayImportError("API error")

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-1", "plan": plan, "case_format": "manual"},
        )

    assert r.status_code == 502


def test_export_xray_non_member_403():
    """XrayConfig.get raises PermissionError → 403."""
    plan = _make_plan()

    with patch("src.api_v2.XrayConfig") as MockConfig:
        mock_cfg_instance = MockConfig.return_value
        mock_cfg_instance.get.side_effect = PermissionError("not a member")

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-foreign", "plan": plan, "case_format": "manual"},
        )

    assert r.status_code == 403


def test_export_xray_no_auth_401():
    """No auth → 401."""
    plan = _make_plan()
    client = make_client(with_user=False)

    r = client.post(
        "/v2/test-plan/export/xray",
        json={"org_id": "org-1", "plan": plan, "case_format": "manual"},
    )
    assert r.status_code == 401


def test_export_xray_forwards_project_key():
    """I1: project_key from the request body is forwarded to import_plan."""
    plan = _make_plan()

    with patch("src.api_v2.XrayConfig") as MockConfig, \
         patch("src.api_v2.XrayClient") as MockClient:
        mock_cfg_instance = MockConfig.return_value
        mock_cfg_instance.get.return_value = _xray_creds()
        mock_client_instance = MockClient.return_value
        mock_client_instance.import_plan.return_value = ["PROJ-1"]

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-1", "plan": plan, "case_format": "gherkin",
                  "project_key": "PROJ"},
        )

    assert r.status_code == 200
    call_kwargs = mock_client_instance.import_plan.call_args.kwargs
    assert call_kwargs.get("project_key") == "PROJ", (
        f"project_key was not forwarded to import_plan; got {call_kwargs}"
    )


def test_export_xray_membership_checked_before_client():
    """XrayConfig.get must be called (with user_id) before XrayClient is instantiated."""
    plan = _make_plan()
    call_order = []

    with patch("src.api_v2.XrayConfig") as MockConfig, \
         patch("src.api_v2.XrayClient") as MockClient:
        mock_cfg_instance = MockConfig.return_value

        def _get_creds(**kw):
            call_order.append("config.get")
            assert kw.get("user_id") == "user-1", "user_id must be passed to config.get"
            return _xray_creds()

        mock_cfg_instance.get.side_effect = _get_creds

        def _client_init(*args, **kw):
            call_order.append("client_init")
            return MagicMock()

        MockClient.side_effect = _client_init
        MockClient.return_value.import_plan.return_value = []

        client = make_client()
        r = client.post(
            "/v2/test-plan/export/xray",
            json={"org_id": "org-1", "plan": plan, "case_format": "manual"},
        )

    assert r.status_code == 200
    assert call_order.index("config.get") < call_order.index("client_init"), (
        "Membership check (config.get) must happen before XrayClient instantiation"
    )
