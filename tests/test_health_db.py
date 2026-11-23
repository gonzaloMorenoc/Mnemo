"""Auditoría 2026-11-23 #20: `/v2/health` respondía "active" sin tocar la BD, así que
el keep-warm salía verde con la BD caída. Ahora comprueba la BD con un `select 1` de
timeout corto cuando DATABASE_URL está configurada (503 si falla) y hay una ruta de
liveness ligera para el HEALTHCHECK del contenedor."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api_v2.router)
    return TestClient(app)


def test_health_sin_database_url_no_toca_la_bd(monkeypatch):
    monkeypatch.setattr(api_v2, "_database_configured", lambda: False)
    boom = MagicMock(side_effect=AssertionError("no debe tocar la BD"))
    monkeypatch.setattr(api_v2, "_ping_database", boom)
    r = _client().get("/v2/health")
    assert r.status_code == 200
    assert r.json()["db"] == "not_configured"


def test_health_con_bd_ok(monkeypatch):
    monkeypatch.setattr(api_v2, "_database_configured", lambda: True)
    monkeypatch.setattr(api_v2, "_ping_database", lambda: None)
    r = _client().get("/v2/health")
    assert r.status_code == 200
    assert r.json()["db"] == "ok" and r.json()["status"] == "active"


def test_health_con_bd_caida_devuelve_503(monkeypatch):
    def _down():
        raise RuntimeError("connection refused: password=secreto")

    monkeypatch.setattr(api_v2, "_database_configured", lambda: True)
    monkeypatch.setattr(api_v2, "_ping_database", _down)
    r = _client().get("/v2/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error" and body["status"] == "degraded"
    assert "secreto" not in r.text      # el error crudo no se expone


def test_liveness_no_toca_la_bd_ni_el_llm(monkeypatch):
    boom = MagicMock(side_effect=AssertionError("no debe tocar la BD"))
    monkeypatch.setattr(api_v2, "_ping_database", boom)
    monkeypatch.setattr(api_v2, "_database_configured", lambda: True)
    r = _client().get("/v2/health/live")
    assert r.status_code == 200 and r.json() == {"status": "alive"}


def test_ping_database_usa_select_1_con_timeout_corto(monkeypatch):
    conn = MagicMock()
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    monkeypatch.setattr(api_v2, "get_pool", lambda: pool)
    api_v2._ping_database()
    pool.connection.assert_called_once_with(timeout=api_v2.HEALTH_DB_TIMEOUT_SECONDS)
    executed = [c.args[0] for c in conn.execute.call_args_list]
    assert any("statement_timeout" in q for q in executed)
    assert executed[-1].strip().lower() == "select 1"
    assert api_v2.HEALTH_DB_TIMEOUT_SECONDS <= 5
