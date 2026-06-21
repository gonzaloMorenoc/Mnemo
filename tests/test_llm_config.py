import importlib


def test_llm_config_defaults(monkeypatch):
    for k in ("LLM_PROVIDER", "LLM_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    import src.config as config
    importlib.reload(config)
    assert config.LLM_PROVIDER == "ollama"
    assert config.LLM_MODEL == "deepseek-r1:8b"
    assert config.OPENAI_API_KEY == ""
    assert config.ANTHROPIC_API_KEY == ""
