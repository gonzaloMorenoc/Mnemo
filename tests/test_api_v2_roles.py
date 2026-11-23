"""Matriz de permisos aplicada a los endpoints de /v2 que escriben
(auditoría 23-nov, #10 /automation/pr, #11 viewer sin aplicar, H8).

viewer → 403 en todo lo que escribe; member → 403 en lo de owner/admin;
owner/admin → pasan la puerta de rol (lo que haga después el servicio es otra suite).
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.orgs.access import OrgAccess, get_org_access
from src.security import AuthenticatedUser

ORG = "org-1"
USER = "user-1"

_SERVICE_DEPS = [
    "get_assurance_repo", "get_ingestion_service", "get_triage_service",
    "get_action_service", "get_certificate_service", "get_continuity_service",
    "get_gate_service", "get_knowledge_repo", "get_knowledge_proposal_service",
    "get_knowledge_import_service", "get_embedder", "get_integrations_repo",
    "get_jira_ingestion_service", "get_ingest_token_repo", "get_github_app_auth",
    "get_root_cause_analyzer", "get_knowledge_proposal_service_optional",
]


class _FixedRole:
    """El usuario tiene `role` en ORG; cualquier recurso pertenece a ORG."""

    def __init__(self, role):
        self.role = role

    def role_of(self, *, org_id, user_id):
        return self.role if (org_id, user_id) == (ORG, USER) else None

    def org_of(self, *, resource, resource_id):
        return ORG


def _client(role):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id=USER, email="u@x.com", claims={})
    app.dependency_overrides[get_org_access] = lambda: OrgAccess(_FixedRole(role))
    mocks = {}
    for name in _SERVICE_DEPS:
        mock = MagicMock(name=name)
        mocks[name] = mock
        app.dependency_overrides[getattr(api_v2, name)] = (lambda m=mock: m)
    return TestClient(app, raise_server_exceptions=False), mocks


def _files():
    return {"file": ("r.xml", b"<testsuite/>", "application/xml")}


# (método, ruta, kwargs de la petición)
QA_WORK = [
    ("post", "/v2/ingest/report", {"data": {"project": "p", "org_id": ORG}, "files": _files()}),
    ("post", "/v2/ingest/jira/file", {"data": {"project": "p", "org_id": ORG}, "files": _files()}),
    ("post", "/v2/ingest/jira/pull", {"json": {"org_id": ORG, "project": "p"}}),
    ("post", "/v2/triage/run/r1/resolve", {}),
    ("patch", "/v2/defects/f1/label", {"json": {"label": "flaky", "reason": "timeout de red"}}),
    ("post", "/v2/defects/f1/root-cause?regenerate=true", {}),
    ("post", "/v2/actions/run/r1/propose", {}),
    ("post", "/v2/defects/ask", {"json": {"org_id": ORG, "question": "¿por qué falla?"}}),
    ("post", "/v2/knowledge", {"json": {"org_id": ORG, "kind": "leccion", "title": "t"}}),
    ("post", "/v2/knowledge/proposals/generate", {"json": {"org_id": ORG}}),
    ("post", "/v2/knowledge/proposals/p1/refine", {}),
    ("post", "/v2/knowledge/import", {"json": {"org_id": ORG, "refs": ["ABC-1"]}}),
    ("patch", "/v2/knowledge/k1", {"json": {"org_id": ORG, "title": "nuevo"}}),
    ("delete", f"/v2/knowledge/k1?org_id={ORG}", {}),
    ("post", "/v2/knowledge/ask", {"json": {"org_id": ORG, "question": "¿cómo?"}}),
    ("post", "/v2/test-plan/generate", {"data": {"org_id": ORG, "hu_text": "Como usuario…"}}),
    ("post", "/v2/test-plan/export/xray", {"json": {"org_id": ORG, "plan": {"cases": []}}}),
    ("post", "/v2/automation/generate", {"json": {"org_id": ORG, "case": {"title": "x"},
                                                  "style_sample": "test()"}}),
    ("post", "/v2/repo/index", {"json": {"org_id": ORG}}),
]

ADMIN = [
    ("post", "/v2/integrations/jira", {"json": {"org_id": ORG, "base_url": "https://x.atlassian.net",
                                                "email": "a@b.c", "token": "t"}}),
    ("post", "/v2/integrations/github", {"json": {"org_id": ORG, "installation_id": "1",
                                                  "repo_full_name": "o/r"}}),
    ("post", "/v2/ingest/tokens", {"json": {"org_id": ORG, "name": "ci"}}),
    ("post", "/v2/ingest/tokens/t1/revoke", {}),
    ("post", "/v2/gate/run/r1", {}),
    ("post", "/v2/actions/a1/approve", {}),
    ("post", "/v2/actions/a1/reject", {"json": {"reason": "no"}}),
    ("post", "/v2/certificates/run/r1", {}),
    ("post", "/v2/continuity/handover", {"json": {"org_id": ORG, "project": "p"}}),
    ("post", "/v2/knowledge/proposals/p1/approve", {"json": {"title": "t"}}),
    ("post", "/v2/knowledge/proposals/p1/reject", {"json": {}}),
    ("post", "/v2/automation/pr", {"json": {"org_id": ORG, "code": "test()",
                                            "filename": "login.spec.ts"}}),
]


def _call(client, method, path, kwargs):
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,kwargs", QA_WORK + ADMIN)
def test_viewer_cannot_write(method, path, kwargs):
    client, _ = _client("viewer")
    resp = _call(client, method, path, kwargs)
    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("method,path,kwargs", ADMIN)
def test_member_cannot_do_admin_actions(method, path, kwargs):
    client, _ = _client("member")
    resp = _call(client, method, path, kwargs)
    assert resp.status_code == 403, resp.text
    assert "owner/admin" in resp.json()["detail"]


@pytest.mark.parametrize("method,path,kwargs", QA_WORK)
def test_member_passes_the_role_gate_for_qa_work(method, path, kwargs):
    client, _ = _client("member")
    with patch("src.api_v2.generate_test_plan", return_value={"citations": []}), \
         patch("src.api_v2.XrayConfig"), patch("src.api_v2.XrayClient"), \
         patch("src.api_v2.TestAssetRepository"), patch("src.api_v2.index_repo_tests",
                                                        return_value={}), \
         patch("src.api_v2._github_codehost_factory"):
        resp = _call(client, method, path, kwargs)
    assert resp.status_code != 403, resp.text


@pytest.mark.parametrize("role", ["admin", "owner"])
@pytest.mark.parametrize("method,path,kwargs", ADMIN)
def test_admins_pass_the_role_gate(role, method, path, kwargs):
    client, mocks = _client(role)
    with patch("src.api_v2._verify_installation_ownership"), \
         patch("src.api_v2._github_codehost_factory"):
        resp = _call(client, method, path, kwargs)
    assert resp.status_code != 403, resp.text


def test_viewer_write_is_refused_before_touching_the_service():
    client, mocks = _client("viewer")
    client.patch("/v2/defects/f1/label", json={"label": "flaky"})
    mocks["get_assurance_repo"].set_family_label.assert_not_called()


# --- #10: /automation/pr sube código al repo del cliente → solo owner/admin -------------

def test_member_cannot_open_automation_pr_and_github_is_not_touched():
    client, _ = _client("member")
    with patch("src.api_v2._github_codehost_factory") as factory:
        resp = client.post("/v2/automation/pr",
                           json={"org_id": ORG, "code": "x", "filename": "a.spec.ts"})
    assert resp.status_code == 403
    factory.assert_not_called()


def test_admin_opens_automation_pr():
    client, _ = _client("admin")
    host = MagicMock()
    host.open_pr_with_new_file.return_value = "https://github.com/o/r/pull/1"
    with patch("src.api_v2._github_codehost_factory", return_value=host):
        resp = client.post("/v2/automation/pr",
                           json={"org_id": ORG, "code": "x", "filename": "a.spec.ts"})
    assert resp.status_code == 200
    assert resp.json() == {"pr_url": "https://github.com/o/r/pull/1"}


def test_automation_generate_requires_membership():
    """Antes llamaba al LLM sin comprobar la pertenencia (H7)."""
    client, _ = _client(None)
    with patch("src.api_v2.generate_playwright_test") as gen:
        resp = client.post("/v2/automation/generate",
                           json={"org_id": ORG, "case": {"title": "x"}, "style_sample": "s"})
    assert resp.status_code == 403
    gen.assert_not_called()


# --- Lecturas: el viewer sigue leyendo ----------------------------------------------------

def test_viewer_can_read_cached_root_cause():
    client, mocks = _client("viewer")
    mocks["get_assurance_repo"].get_family_with_failures.return_value = {
        "family": {"root_cause": "causa ya calculada", "org_id": ORG}, "failures": []}
    resp = client.post("/v2/defects/f1/root-cause")
    assert resp.status_code == 200
    assert resp.json()["cached"] is True


def test_viewer_cannot_compute_a_new_root_cause():
    client, mocks = _client("viewer")
    mocks["get_assurance_repo"].get_family_with_failures.return_value = {
        "family": {"root_cause": None, "org_id": ORG}, "failures": []}
    resp = client.post("/v2/defects/f1/root-cause")
    assert resp.status_code == 403
    mocks["get_root_cause_analyzer"].analyze_structured.assert_not_called()


def test_viewer_can_search_knowledge():
    client, _ = _client("viewer")
    with patch("src.api_v2.KnowledgeService") as svc:
        svc.return_value.search_unified.return_value = []
        resp = client.post("/v2/knowledge/search", json={"org_id": ORG, "query": "login"})
    assert resp.status_code == 200
