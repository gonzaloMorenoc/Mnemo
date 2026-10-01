"""POST /v2/orgs/join: freno a la fuerza bruta del código de unión (40 bits).

Por usuario autenticado y no por IP: todo el tráfico del navegador llega por el
proxy de Vercel, así que un límite por IP frenaría a todos a la vez."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _client(repo, user_id="u1"):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_repo] = lambda: repo
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id=user_id, email="e@x.com", claims={})
    return TestClient(app)


def test_too_many_wrong_codes_are_throttled_without_touching_the_db(monkeypatch):
    monkeypatch.setattr(api_v2, "_join_failures", {})
    repo = MagicMock()
    repo.join_organization.side_effect = ValueError("código no válido")
    c = _client(repo)
    for _ in range(api_v2._JOIN_MAX_FAILURES):
        assert c.post("/v2/orgs/join", json={"join_code": "deadbeef00"}).status_code == 404
    r = c.post("/v2/orgs/join", json={"join_code": "deadbeef00"})
    assert r.status_code == 429
    assert repo.join_organization.call_count == api_v2._JOIN_MAX_FAILURES


def test_the_limit_is_per_user(monkeypatch):
    monkeypatch.setattr(api_v2, "_join_failures", {})
    repo = MagicMock()
    repo.join_organization.side_effect = ValueError("código no válido")
    for _ in range(api_v2._JOIN_MAX_FAILURES):
        _client(repo, "atacante").post("/v2/orgs/join", json={"join_code": "x" * 10})
    assert _client(repo, "otro").post("/v2/orgs/join", json={"join_code": "x" * 10}).status_code == 404


def test_failures_expire_after_the_window(monkeypatch):
    monkeypatch.setattr(api_v2, "_join_failures", {})
    now = [1000.0]
    monkeypatch.setattr(api_v2, "_join_clock", lambda: now[0])
    repo = MagicMock()
    repo.join_organization.side_effect = ValueError("código no válido")
    c = _client(repo)
    for _ in range(api_v2._JOIN_MAX_FAILURES):
        c.post("/v2/orgs/join", json={"join_code": "x" * 10})
    now[0] += api_v2._JOIN_WINDOW_SECONDS + 1
    assert c.post("/v2/orgs/join", json={"join_code": "x" * 10}).status_code == 404
