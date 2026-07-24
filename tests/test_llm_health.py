"""Diagnóstico del LLM para /v2/health: distingue 'no configurado' (falta una env)
de 'no alcanzable' (la llamada a la API falla). Cierra la caja negra de 'LLM no disponible'."""
from src import config
from src.llm import factory
from src.llm.factory import llm_status


def _openai_ok(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    monkeypatch.setattr(config, "LLM_MODEL", "gemini-2.5-flash")


def test_status_configured_when_provider_builds(monkeypatch):
    _openai_ok(monkeypatch)
    s = llm_status()
    assert s["provider"] == "openai"
    assert s["model"] == "gemini-2.5-flash"
    assert s["configured"] is True
    assert s["error"] is None
    assert s["reachable"] is None  # sin probe no se llama a la API


def test_status_reports_missing_key(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    s = llm_status()
    assert s["configured"] is False
    assert "OPENAI_API_KEY" in s["error"]


def test_status_reports_missing_optin(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", False)
    s = llm_status()
    assert s["configured"] is False
    assert "ALLOW_EXTERNAL_LLM" in s["error"]


class _FakeOK:
    def complete(self, prompt):
        return "pong"


class _FakeBoom:
    def complete(self, prompt):
        raise RuntimeError("Error code: 400 - Please pass a valid API key")


def test_probe_reachable_true(monkeypatch):
    _openai_ok(monkeypatch)
    monkeypatch.setattr(factory, "get_llm_provider", lambda: _FakeOK())
    s = llm_status(probe=True)
    assert s["configured"] is True
    assert s["reachable"] is True
    assert s["error"] is None


def test_probe_reports_real_call_error(monkeypatch):
    _openai_ok(monkeypatch)
    monkeypatch.setattr(factory, "get_llm_provider", lambda: _FakeBoom())
    s = llm_status(probe=True)
    assert s["configured"] is True
    assert s["reachable"] is False
    assert "valid API key" in s["error"]


def test_generate_structured_logs_the_swallowed_error(caplog):
    """El fallo del LLM degrada (no lanza) PERO ahora deja rastro en el log."""
    import logging
    from src.ai.generate import generate_structured

    with caplog.at_level(logging.WARNING):
        out = generate_structured(prompt="p", context=[], schema={"answer": ""},
                                  provider=_FakeBoom(), on_failure="none")
    assert out is None
    assert any("no alcanzable" in r.getMessage() and "valid API key" in r.getMessage()
               for r in caplog.records)
