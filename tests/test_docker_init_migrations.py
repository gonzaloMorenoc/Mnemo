import importlib

from src.db.migrate import load_migrations


def test_docker_init_usa_el_runner_con_todas_las_migraciones(monkeypatch):
    for k in ("DATABASE_URL", "SUPABASE_URL", "SERVICE_ROLE_KEY", "DEMO_EMAIL", "DEMO_PASSWORD"):
        monkeypatch.setenv(k, "dummy")
    import scripts.docker_init as di
    importlib.reload(di)
    names = [m.filename for m in load_migrations(di.MIGRATIONS_DIR)]
    assert any(n.startswith("016_") for n in names), "faltan las migraciones del Autopilot (007-016)"
    assert any(n.startswith("002_assurance") for n in names)
    assert names == sorted(names), "las migraciones deben aplicarse en orden"
    assert names[-1].startswith("999_"), "la 999 (cierre de la Data API) va siempre al final"
    assert di.migrate is not None   # mismo runner que el despliegue
