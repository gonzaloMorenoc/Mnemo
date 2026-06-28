import pytest

from src import config
from src.llm.factory import get_llm_provider, _DEFAULT_MODELS
from src.llm.providers.ollama import OllamaProvider
from src.llm.providers.openai import OpenAIProvider
from src.llm.providers.anthropic import AnthropicProvider


def test_default_ollama(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "ollama")
    assert isinstance(get_llm_provider(), OllamaProvider)


def test_openai(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    assert isinstance(get_llm_provider(), OpenAIProvider)


def test_anthropic(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    assert isinstance(get_llm_provider(), AnthropicProvider)


def test_openai_without_key_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        get_llm_provider()


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "foobar")
    with pytest.raises(ValueError):
        get_llm_provider()


def test_openai_uses_default_model_when_unset(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "LLM_MODEL", "")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    p = get_llm_provider()
    assert p._model and p._model != "qwen3:8b"


def test_provider_name_is_stripped(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "  ollama ")
    assert isinstance(get_llm_provider(), OllamaProvider)


def test_commercial_provider_requires_optin(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", False)
    with pytest.raises(RuntimeError):
        get_llm_provider()


def test_commercial_provider_with_optin_ok(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(config, "ALLOW_EXTERNAL_LLM", True)
    assert isinstance(get_llm_provider(), AnthropicProvider)


def test_anthropic_default_is_current_model():
    assert _DEFAULT_MODELS["anthropic"] == "claude-haiku-4-5-20251001"
    assert "3-5" not in _DEFAULT_MODELS["anthropic"]   # ya no el alias obsoleto


def test_ollama_default_is_qwen3():
    assert _DEFAULT_MODELS["ollama"] == "qwen3:8b"   # default on-prem: JSON estructurado + español + rápido
