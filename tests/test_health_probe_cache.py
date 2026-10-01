"""`/v2/health?probe=1` es público y hace una llamada REAL al LLM: sin freno, un
bucle de peticiones vaciaba la cuota del LLM (el free tier de la demo) justo cuando
alguien la estaba probando. El probe real sale como mucho una vez por ventana."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2


def _client():
    app = FastAPI()
    app.include_router(api_v2.router)
    return TestClient(app)


def test_probe_hits_the_llm_at_most_once_per_window(monkeypatch):
    calls = []

    def fake_status(*, probe=False):
        calls.append(probe)
        return {"configured": True, "reachable": True if probe else None}

    monkeypatch.setattr(api_v2, "llm_status", fake_status)
    monkeypatch.setattr(api_v2, "_probe_cache", None)
    c = _client()
    for _ in range(5):
        assert c.get("/v2/health?probe=1").json()["llm"]["reachable"] is True
    assert calls.count(True) == 1


def test_probe_is_repeated_after_the_window(monkeypatch):
    calls = []
    monkeypatch.setattr(api_v2, "llm_status",
                        lambda *, probe=False: calls.append(probe) or {"reachable": probe})
    monkeypatch.setattr(api_v2, "_probe_cache", None)
    now = [1000.0]
    monkeypatch.setattr(api_v2, "_monotonic", lambda: now[0])
    c = _client()
    c.get("/v2/health?probe=1")
    now[0] += api_v2._PROBE_TTL_SECONDS + 1
    c.get("/v2/health?probe=1")
    assert calls.count(True) == 2


def test_plain_health_never_probes(monkeypatch):
    calls = []
    monkeypatch.setattr(api_v2, "llm_status",
                        lambda *, probe=False: calls.append(probe) or {"reachable": None})
    _client().get("/v2/health")
    assert calls == [False]
