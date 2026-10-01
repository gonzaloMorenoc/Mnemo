"""Propuestas de conocimiento tras una ingesta (BackgroundTask, auditoría 12-ago H4a).

Corre después de responder al CI: nunca puede romper la ingesta ni gastar el lote
en fallbacks cuando no hay LLM.
"""
import logging
from unittest.mock import MagicMock

import src.api_v2 as api_v2


def _with(monkeypatch, *, service, configured=True):
    monkeypatch.setattr(api_v2, "get_knowledge_proposal_service_optional", lambda: service)
    monkeypatch.setattr(api_v2, "llm_status", lambda: {"configured": configured})


def test_generates_with_the_capped_batch(monkeypatch):
    svc = MagicMock()
    svc.generate.return_value = {"created": 2}
    _with(monkeypatch, service=svc)
    api_v2._propose_knowledge_after_ingest("u", "o")
    svc.generate.assert_called_once_with(user_id="u", org_id="o",
                                         cap=api_v2._PROPOSAL_CAP_POST_INGEST)


def test_skips_without_llm(monkeypatch):
    svc = MagicMock()
    _with(monkeypatch, service=svc, configured=False)
    api_v2._propose_knowledge_after_ingest("u", "o")
    svc.generate.assert_not_called()


def test_skips_without_multitenant(monkeypatch):
    _with(monkeypatch, service=None)
    api_v2._propose_knowledge_after_ingest("u", "o")  # no lanza


def test_failure_is_logged_not_raised(monkeypatch, caplog):
    svc = MagicMock()
    svc.generate.side_effect = RuntimeError("LLM caído")
    _with(monkeypatch, service=svc)
    with caplog.at_level(logging.ERROR, logger=api_v2.logger.name):
        api_v2._propose_knowledge_after_ingest("u", "o")
    assert "propuestas post-ingesta fallaron" in caplog.text
