import importlib
import os


def test_migrations_glob_includes_all(monkeypatch):
    for k in ("DATABASE_URL", "SUPABASE_URL", "SERVICE_ROLE_KEY", "DEMO_EMAIL", "DEMO_PASSWORD"):
        monkeypatch.setenv(k, "dummy")
    import scripts.docker_init as di
    importlib.reload(di)
    migs = di.MIGRATIONS
    # recoge todas las migraciones del directorio, no solo 001-006
    assert any("016" in m for m in migs), "faltan las migraciones del Autopilot (007-016)"
    assert any("002_assurance" in m for m in migs)
    assert migs == sorted(migs), "las migraciones deben aplicarse en orden"
    assert len(migs) >= 16
