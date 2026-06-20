import importlib


def test_config_defines_multitenant_constants():
    import src.config as config
    importlib.reload(config)
    assert hasattr(config, "DATABASE_URL")
    assert hasattr(config, "UPLOAD_DIR")
    assert isinstance(config.DEFAULT_TOP_K, int) and config.DEFAULT_TOP_K >= 1
    assert hasattr(config, "SUPABASE_URL")
    assert hasattr(config, "SUPABASE_JWKS_URL")
    assert hasattr(config, "SUPABASE_JWT_AUDIENCE")


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


def test_multitenant_modules_import():
    import src.tenant_kb  # noqa: F401
    import src.security  # noqa: F401
    import src.structured_analyzer  # noqa: F401
    import src.multitenant_models  # noqa: F401
    import src.sanitizer  # noqa: F401
    import src.scope_priority  # noqa: F401
