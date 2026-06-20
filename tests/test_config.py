import importlib


def test_config_defaults_when_env_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_AUDIENCE", raising=False)
    monkeypatch.delenv("DEFAULT_TOP_K", raising=False)
    # Neutralise load_dotenv so it cannot re-populate os.environ from .env
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda **kw: None)
    import src.config as config
    importlib.reload(config)
    assert config.DATABASE_URL == ""
    assert config.SUPABASE_URL == ""
    assert config.SUPABASE_JWKS_URL == ""
    assert config.SUPABASE_JWT_AUDIENCE == ""
    assert isinstance(config.DEFAULT_TOP_K, int)
    assert config.DEFAULT_TOP_K == 8


def test_multi_tenant_enabled_false_when_unset(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    assert config.multi_tenant_enabled() is False


def test_multi_tenant_enabled_true_when_set(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    assert config.multi_tenant_enabled() is True
