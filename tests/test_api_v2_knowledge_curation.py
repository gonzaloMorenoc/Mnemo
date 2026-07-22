"""Tests de los endpoints de curación: PATCH/DELETE /v2/knowledge/{id} + filtros del GET."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(repo):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_knowledge_repo] = lambda: repo
    return TestClient(app)


ITEM = {"id": "k1", "kind": "leccion", "title": "T", "status": "activo",
        "tags": [], "confidence": "confirmado", "created_at": "2026-07-22T00:00:00"}


def test_patch_updates_and_returns_item():
    repo = MagicMock()
    repo.update_item.return_value = dict(ITEM, title="Editado")
    client = make_client(repo)
    r = client.patch("/v2/knowledge/k1", json={"org_id": "o1", "title": "Editado"})
    assert r.status_code == 200 and r.json()["title"] == "Editado"
    kw = repo.update_item.call_args.kwargs
    assert kw["item_id"] == "k1" and kw["org_id"] == "o1"
    assert kw["fields"] == {"title": "Editado"}       # exclude_none: solo lo enviado


def test_patch_status_obsoleto():
    repo = MagicMock()
    repo.update_item.return_value = dict(ITEM, status="obsoleto")
    client = make_client(repo)
    r = client.patch("/v2/knowledge/k1", json={"org_id": "o1", "status": "obsoleto"})
    assert r.status_code == 200 and r.json()["status"] == "obsoleto"


def test_patch_none_is_404():
    repo = MagicMock()
    repo.update_item.return_value = None              # sin permiso o no existe
    client = make_client(repo)
    r = client.patch("/v2/knowledge/k1", json={"org_id": "o1", "title": "x"})
    assert r.status_code == 404


def test_patch_invalid_value_is_400():
    repo = MagicMock()
    repo.update_item.side_effect = ValueError("status inválido")
    client = make_client(repo)
    r = client.patch("/v2/knowledge/k1", json={"org_id": "o1", "status": "borrado"})
    assert r.status_code == 400


def test_delete_ok():
    repo = MagicMock()
    repo.delete_item.return_value = True
    client = make_client(repo)
    r = client.delete("/v2/knowledge/k1", params={"org_id": "o1"})
    assert r.status_code == 200 and r.json() == {"deleted": True}


def test_delete_no_permission_is_404():
    repo = MagicMock()
    repo.delete_item.return_value = False
    client = make_client(repo)
    r = client.delete("/v2/knowledge/k1", params={"org_id": "o1"})
    assert r.status_code == 404


def test_list_passes_project_and_status_filters():
    repo = MagicMock()
    repo.list_items.return_value = []
    client = make_client(repo)
    r = client.get("/v2/knowledge", params={"org_id": "o1", "project": "web",
                                            "status": "obsoleto"})
    assert r.status_code == 200
    kw = repo.list_items.call_args.kwargs
    assert kw["project"] == "web" and kw["status"] == "obsoleto"
