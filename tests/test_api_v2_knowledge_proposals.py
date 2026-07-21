"""Tests for /v2/knowledge/proposals endpoints (auto-memoria — IA propone / humano aprueba)."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(svc):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_knowledge_proposal_service] = lambda: svc
    return TestClient(app)


def test_list_proposals_returns_tray():
    svc = MagicMock()
    svc.list.return_value = [{"id": "p1", "title": "T", "status": "pending"}]
    client = make_client(svc)
    r = client.get("/v2/knowledge/proposals", params={"org_id": "o1"})
    assert r.status_code == 200
    assert r.json()[0]["id"] == "p1"
    # la ruta estática gana a /knowledge/{item_id}: se llamó a list, no a get_item
    svc.list.assert_called_once_with(user_id="user-1", org_id="o1", status="pending")


def test_generate_returns_counts():
    svc = MagicMock()
    svc.generate.return_value = {"created": 2, "failed": 0, "remaining": 3}
    client = make_client(svc)
    r = client.post("/v2/knowledge/proposals/generate", json={"org_id": "o1", "cap": 5})
    assert r.status_code == 200
    assert r.json() == {"created": 2, "failed": 0, "remaining": 3}
    assert svc.generate.call_args.kwargs["cap"] == 5


def test_approve_returns_created_item():
    svc = MagicMock()
    svc.approve.return_value = {"id": "k1", "kind": "leccion", "title": "T"}
    client = make_client(svc)
    r = client.post("/v2/knowledge/proposals/p1/approve",
                    json={"kind": "leccion", "title": "T", "challenge": "c", "approach": "a",
                          "domain": "d", "outcome": "o", "tags": ["x"]})
    assert r.status_code == 200 and r.json()["id"] == "k1"
    assert svc.approve.call_args.kwargs["proposal_id"] == "p1"


def test_approve_none_is_403():
    svc = MagicMock()
    svc.approve.return_value = None            # no pendiente o no owner/admin
    client = make_client(svc)
    r = client.post("/v2/knowledge/proposals/p1/approve", json={"title": "T"})
    assert r.status_code == 403


def test_reject_ok():
    svc = MagicMock()
    svc.reject.return_value = True
    client = make_client(svc)
    r = client.post("/v2/knowledge/proposals/p1/reject", json={"reason": "dup"})
    assert r.status_code == 200 and r.json() == {"rejected": True}
    assert svc.reject.call_args.kwargs["reason"] == "dup"


def test_reject_false_is_403():
    svc = MagicMock()
    svc.reject.return_value = False
    client = make_client(svc)
    r = client.post("/v2/knowledge/proposals/p1/reject", json={})
    assert r.status_code == 403
