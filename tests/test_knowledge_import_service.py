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


def test_parse_refs_claves_validas_e_invalidas():
    parsed, errors = parse_refs(["PAY-123", "pay-1", "PROJ-", "1ABC-2",
                                 "https://a.atlassian.net/wiki/spaces/QA/pages/99/T"])
    assert [p.key for p in parsed] == ["PAY-123"]
    assert parsed[0].external_ref == "jira:PAY-123"
    # PR1: las URLs de Confluence se rechazan con mensaje claro, no se ignoran
    reasons = " ".join(e.reason for e in errors)
    assert "Confluence" in reasons
    assert len(errors) == 4


def test_parse_refs_dedupe_y_espacios():
    parsed, errors = parse_refs([" PAY-1 ", "PAY-1", "", "  "])
    assert [p.key for p in parsed] == ["PAY-1"]
    assert errors == []


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
