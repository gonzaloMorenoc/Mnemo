"""Smoke test: the multi-tenant modules import cleanly (guards against ImportError regressions)."""


def test_multitenant_modules_import():
    import src.tenant_kb  # noqa: F401
    import src.security  # noqa: F401
    import src.structured_analyzer  # noqa: F401
    import src.multitenant_models  # noqa: F401
    import src.sanitizer  # noqa: F401
    import src.scope_priority  # noqa: F401
