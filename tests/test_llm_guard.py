"""Punto de salida al LLM externo (auditoría 23-nov, #17): saneado centralizado e
interruptor por organización."""
import pytest

from src import config
from src.llm import org_policy
from src.llm.factory import get_llm_provider
from src.llm.guard import ExternalLLMGuard
from src.llm.org_policy import (
    ExternalLLMDisabledForOrg,
    bind_llm_org_lazy,
    external_llm_allowed,
    llm_org_scope,
)
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider

_JWT = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")


class _Recorder:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"


@pytest.fixture(autouse=True)
def _clean_cache():
    org_policy.invalidate_policy_cache()
    yield
    org_policy.invalidate_policy_cache()


def test_el_prompt_sale_saneado():
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: True)
    guard.complete(f"HU pegada: Authorization: Bearer {_JWT}\nDNI 12345678Z, tel +34 612 345 678")
    sent = inner.prompts[0]
    assert _JWT not in sent and "12345678Z" not in sent and "612 345 678" not in sent


def test_el_saneado_de_salida_no_rompe_codigo_ni_urls():
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: True)
    code = ("import { test } from '@playwright/test';\n"
            "await page.goto('https://shop.example.com/login');\n"
            "await page.locator('#submit').click(); // tests/e2e/login.spec.ts")
    guard.complete(code)
    assert inner.prompts[0] == code


def test_org_con_llm_externo_desactivado_no_llama_al_proveedor():
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: org != "org-no")
    with llm_org_scope("org-no"):
        with pytest.raises(ExternalLLMDisabledForOrg):
            guard.complete("hola")
    assert inner.prompts == []


def test_org_con_llm_permitido_llama():
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: org != "org-no")
    with llm_org_scope("org-si"):
        assert guard.complete("hola") == "ok"


def test_sin_org_fijada_solo_cuenta_la_politica_global():
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: False)
    assert guard.complete("hola") == "ok"


def test_el_ambito_no_se_filtra_fuera_del_bloque():
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: False)
    with llm_org_scope("org-no"):
        pass
    assert guard.complete("hola") == "ok"


def test_resolver_perezoso_solo_se_llama_al_usar_el_llm():
    import contextvars
    calls = []

    def _run():
        bind_llm_org_lazy(lambda: calls.append(1) or "org-no")
        assert calls == []          # fijar el ámbito no consulta nada
        guard = ExternalLLMGuard(_Recorder(), policy=lambda org: False)
        with pytest.raises(ExternalLLMDisabledForOrg):
            guard.complete("x")
        with pytest.raises(ExternalLLMDisabledForOrg):
            guard.complete("y")
        assert calls == [1]         # se resuelve una vez por petición

    contextvars.copy_context().run(_run)


def test_si_no_se_puede_resolver_la_org_falla_cerrado():
    import contextvars

    def _boom():
        raise RuntimeError("BD caída")

    def _run():
        bind_llm_org_lazy(_boom)
        guard = ExternalLLMGuard(_Recorder(), policy=lambda org: True)
        with pytest.raises(ExternalLLMDisabledForOrg):
            guard.complete("x")

    contextvars.copy_context().run(_run)


def test_politica_ilegible_falla_cerrado():
    def _reader(org):
        raise RuntimeError("BD caída")
    assert external_llm_allowed("o1", reader=_reader) is False


def test_politica_cacheada():
    calls = []

    def _reader(org):
        calls.append(org)
        return False

    assert external_llm_allowed("o1", reader=_reader) is False
    assert external_llm_allowed("o1", reader=_reader) is False
    assert calls == ["o1"]
    org_policy.invalidate_policy_cache("o1")
    external_llm_allowed("o1", reader=_reader)
    assert calls == ["o1", "o1"]


def test_factoria_envuelve_los_proveedores_externos(monkeypatch):
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    p = get_llm_provider()
    assert isinstance(p, ExternalLLMGuard) and isinstance(p.inner, OpenAIProvider)
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    p = get_llm_provider()
    assert isinstance(p, ExternalLLMGuard) and isinstance(p.inner, AnthropicProvider)


def test_factoria_no_envuelve_ollama_local(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    assert isinstance(get_llm_provider(), OllamaProvider)


def test_generate_structured_degrada_si_la_org_lo_desactiva():
    from src.ai.generate import generate_structured
    guard = ExternalLLMGuard(_Recorder(), policy=lambda org: False)
    with llm_org_scope("org-no"):
        out = generate_structured(prompt="p", context=[], schema={"a": "def"},
                                  provider=guard, on_failure="none")
    assert out is None
