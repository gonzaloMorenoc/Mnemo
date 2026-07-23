"""Servicio de import: parseo estricto de refs, borrador determinista (sin LLM),
URL derivada del base_url configurado (jamás la pegada), cap 10, tope horario,
errores por-ref que no abortan el lote."""
from unittest.mock import MagicMock

import pytest

from src.jira.client import JiraApiError
from src.jira.models import JiraIssue
from src.knowledge.import_service import (
    ImportNotConfigured, ImportRateLimited, KnowledgeImportService, parse_refs)


ISSUE_OK = JiraIssue(
    key="PAY-1", summary="Cobro duplicado", description="Al reintentar el pago…",
    acceptance_criteria="No debe duplicar cargos", resolution="Fixed",
    resolution_date="2026-07-01T10:00:00.000+0000")


BASE = "https://a.atlassian.net"


def test_parse_refs_claves_validas_e_invalidas():
    parsed, errors = parse_refs(["PAY-123", "pay-1", "PROJ-", "1ABC-2"], BASE)
    assert [p.key for p in parsed] == ["PAY-123"]
    assert parsed[0].external_ref == "jira:PAY-123"
    assert len(errors) == 3


def test_parse_refs_dedupe_y_espacios():
    parsed, errors = parse_refs([" PAY-1 ", "PAY-1", "", "  "], BASE)
    assert [p.key for p in parsed] == ["PAY-1"]
    assert errors == []


def test_parse_refs_url_confluence_del_site_configurado():
    parsed, errors = parse_refs([f"{BASE}/wiki/spaces/QA/pages/99/Titulo"], BASE)
    assert errors == []
    assert parsed[0].source == "confluence"
    assert parsed[0].key == "99"
    assert parsed[0].external_ref == "confluence:99"


def test_parse_refs_url_de_otro_site_error_por_ref():
    parsed, errors = parse_refs(
        ["https://otro.atlassian.net/wiki/spaces/QA/pages/99/T"], BASE)
    assert parsed == []
    assert len(errors) == 1
    assert "otro site" in errors[0].reason


def test_parse_refs_dedupe_de_paginas():
    parsed, _ = parse_refs(
        [f"{BASE}/wiki/spaces/QA/pages/99/T", f"{BASE}/wiki/pages/99/otro-titulo"], BASE)
    assert len(parsed) == 1


def _service(issue=ISSUE_OK, recent=0, upsert_result=None, creds="ok"):
    repo = MagicMock()
    repo.count_recent_imports.return_value = recent
    repo.upsert_import_proposal.return_value = upsert_result
    integrations = MagicMock()
    integrations.get_jira_credentials.return_value = None if creds is None else {
        "base_url": "https://a.atlassian.net", "email": "e@x.com", "token": "t",
        "jql": ""}
    client = MagicMock()
    client.fetch_issue.return_value = issue
    svc = KnowledgeImportService(repo=repo, integrations=integrations,
                                 client_factory=lambda creds: client)
    return svc, repo, client


def test_import_crea_propuesta_determinista():
    svc, repo, _ = _service(upsert_result={"id": "p1", "created": True})
    out = svc.import_refs(user_id="u1", org_id="o1", refs=["PAY-1"])
    assert [c["id"] for c in out["created"]] == ["p1"]
    assert out["refreshed"] == [] and out["skipped"] == [] and out["errors"] == []
    kwargs = repo.upsert_import_proposal.call_args.kwargs
    assert kwargs["source"] == "jira"
    assert kwargs["external_ref"] == "jira:PAY-1"
    # URL DERIVADA del base_url configurado, no de nada pegado
    assert kwargs["external_url"] == "https://a.atlassian.net/browse/PAY-1"
    assert kwargs["project"] == "PAY"
    assert kwargs["tags"] == ["PAY"]
    assert kwargs["title"] == "Cobro duplicado"
    assert kwargs["challenge"] == "Al reintentar el pago…"
    assert kwargs["approach"] == "No debe duplicar cargos"  # criterios → embedding
    assert "Fixed" in kwargs["outcome"] and "2026-07-01" in kwargs["outcome"]
    assert kwargs["kind"] == "leccion"


def test_import_refrescada_y_omitida():
    svc, repo, _ = _service()
    repo.upsert_import_proposal.side_effect = [
        {"id": "p1", "created": False},   # refrescada
        None,                             # ya aprobada/rechazada → omitida
    ]
    out = svc.import_refs(user_id="u1", org_id="o1", refs=["PAY-1", "PAY-2"])
    assert [r["id"] for r in out["refreshed"]] == ["p1"]
    assert out["skipped"] == ["PAY-2"]


def test_cap_10():
    svc, _, _ = _service()
    with pytest.raises(ValueError):
        svc.import_refs(user_id="u1", org_id="o1",
                        refs=[f"PAY-{i}" for i in range(11)])


def test_tope_horario():
    svc, _, _ = _service(recent=30)
    with pytest.raises(ImportRateLimited):
        svc.import_refs(user_id="u1", org_id="o1", refs=["PAY-1"])


def test_error_por_ref_no_aborta_lote():
    svc, repo, client = _service(upsert_result={"id": "p1", "created": True})
    client.fetch_issue.side_effect = [JiraApiError("404 Not Found"), ISSUE_OK]
    out = svc.import_refs(user_id="u1", org_id="o1", refs=["PAY-9", "PAY-1"])
    assert len(out["errors"]) == 1
    assert out["errors"][0]["ref"] == "PAY-9"
    assert "404" in out["errors"][0]["reason"]
    assert len(out["created"]) == 1


def test_sin_credenciales():
    svc, _, _ = _service(creds=None)
    with pytest.raises(ImportNotConfigured):
        svc.import_refs(user_id="u1", org_id="o1", refs=["PAY-1"])


def test_refs_invalidas_no_cuentan_para_el_tope():
    """Solo las refs parseables consumen tope: 30 recientes + 0 parseables no lanza."""
    svc, _, _ = _service(recent=30)
    out = svc.import_refs(user_id="u1", org_id="o1", refs=["no-valida"])
    assert out["created"] == [] and len(out["errors"]) == 1


# ── Confluence (PR2) ─────────────────────────────────────────────────────────

from src.confluence.client import ConfluenceApiError, ConfluencePage  # noqa: E402

PAGE_OK = ConfluencePage(id="99", title="Reglas de pagos",
                         text="Regla 1: nunca duplicar cargos. " * 10,
                         space_key="QA")


def _service_confluence(page=PAGE_OK, upsert_result=None):
    repo = MagicMock()
    repo.count_recent_imports.return_value = 0
    repo.upsert_import_proposal.return_value = upsert_result
    integrations = MagicMock()
    integrations.get_jira_credentials.return_value = {
        "base_url": "https://a.atlassian.net", "email": "e@x.com", "token": "t",
        "jql": ""}
    confluence = MagicMock()
    confluence.fetch_page.return_value = page
    svc = KnowledgeImportService(
        repo=repo, integrations=integrations,
        client_factory=lambda creds: MagicMock(),
        confluence_client_factory=lambda creds: confluence)
    return svc, repo, confluence


def test_import_pagina_confluence_crea_propuesta():
    svc, repo, confluence = _service_confluence(
        upsert_result={"id": "p9", "created": True})
    out = svc.import_refs(user_id="u1", org_id="o1",
                          refs=["https://a.atlassian.net/wiki/spaces/QA/pages/99/T"])
    assert [c["id"] for c in out["created"]] == ["p9"]
    confluence.fetch_page.assert_called_once_with("99")
    kwargs = repo.upsert_import_proposal.call_args.kwargs
    assert kwargs["source"] == "confluence"
    assert kwargs["external_ref"] == "confluence:99"
    # URL derivada del base_url configurado por pageId — no la pegada
    assert kwargs["external_url"] == \
        "https://a.atlassian.net/wiki/pages/viewpage.action?pageId=99"
    assert kwargs["title"] == "Reglas de pagos"
    assert kwargs["tags"] == ["QA"]
    assert kwargs["project"] is None
    assert kwargs["approach"] is None
    assert kwargs["challenge"].startswith("Regla 1")


def test_import_pagina_larga_trunca_con_marca():
    page = ConfluencePage(id="99", title="Larga", text="x" * 5000, space_key="QA")
    svc, repo, _ = _service_confluence(page=page,
                                       upsert_result={"id": "p9", "created": True})
    svc.import_refs(user_id="u1", org_id="o1",
                    refs=["https://a.atlassian.net/wiki/pages/99/T"])
    challenge = repo.upsert_import_proposal.call_args.kwargs["challenge"]
    assert len(challenge) <= 2100
    assert challenge.endswith("[contenido truncado — ver original]")


def test_confluence_sin_licencia_error_por_ref_no_502():
    svc, repo, confluence = _service_confluence()
    confluence.fetch_page.side_effect = ConfluenceApiError("404 Not Found")
    out = svc.import_refs(user_id="u1", org_id="o1",
                          refs=["https://a.atlassian.net/wiki/pages/99/T"])
    assert len(out["errors"]) == 1
    assert "Confluence" in out["errors"][0]["reason"]
    assert out["created"] == []
    repo.upsert_import_proposal.assert_not_called()


def test_lote_mixto_jira_y_confluence():
    svc, repo, _ = _service_confluence(upsert_result={"id": "p", "created": True})
    jira_client = MagicMock()
    jira_client.fetch_issue.return_value = ISSUE_OK
    svc._client_factory = lambda creds: jira_client
    out = svc.import_refs(user_id="u1", org_id="o1",
                          refs=["PAY-1", "https://a.atlassian.net/wiki/pages/99/T"])
    assert len(out["created"]) == 2
    sources = [c.kwargs["source"] for c in repo.upsert_import_proposal.call_args_list]
    assert sorted(sources) == ["confluence", "jira"]
