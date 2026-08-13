"""Endpoints de continuidad: índice, emisión del acta y última acta."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.certify.signing import SigningKeyMissing
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


_IDX = {"score": 50, "dimensions": [], "inventario": {}}


def make_client(monkeypatch, svc=None, index=_IDX, projects=()):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    if svc is not None:
        app.dependency_overrides[api_v2.get_continuity_service] = lambda: svc
    monkeypatch.setattr(api_v2, "compute_index", lambda **kw: index)
    monkeypatch.setattr(api_v2, "list_projects", lambda **kw: list(projects))
    return TestClient(app)


def test_get_sin_project_lista_proyectos(monkeypatch):
    client = make_client(monkeypatch, projects=["a", "b"])
    r = client.get("/v2/continuity", params={"org_id": "o1"})
    assert r.status_code == 200
    assert r.json() == {"projects": ["a", "b"]}


def test_get_con_project_devuelve_el_indice(monkeypatch):
    client = make_client(monkeypatch, projects=["checkout"])
    r = client.get("/v2/continuity", params={"org_id": "o1", "project": "checkout"})
    assert r.status_code == 200
    assert r.json()["score"] == 50


def test_get_proyecto_desconocido_404(monkeypatch):
    client = make_client(monkeypatch, projects=["otro"])
    r = client.get("/v2/continuity", params={"org_id": "o1", "project": "checkout"})
    assert r.status_code == 404


def test_get_no_miembro_404(monkeypatch):
    """compute_index devuelve None si no es miembro: mismo 404 que un proyecto
    ajeno, para no filtrar qué orgs existen."""
    client = make_client(monkeypatch, index=None, projects=["checkout"])
    r = client.get("/v2/continuity", params={"org_id": "o1", "project": "checkout"})
    assert r.status_code == 404


def test_emitir_feliz(monkeypatch):
    svc = MagicMock()
    svc.emit_handover.return_value = {"canonical_json": {"schema": "mnemo.traspaso.v1"},
                                      "signature": "s", "share": "blob", "score": 50,
                                      "created_at": "2026-08-13T10:00:00Z"}
    client = make_client(monkeypatch, svc=svc)
    r = client.post("/v2/continuity/handover", json={"org_id": "o1", "project": "checkout"})
    assert r.status_code == 200
    assert r.json()["share"] == "blob"
    kwargs = svc.emit_handover.call_args.kwargs
    assert kwargs["user_id"] == "user-1" and kwargs["project"] == "checkout"
    # created_at lo pone el endpoint (UTC), nunca la lógica firmada
    assert kwargs["created_at"].endswith("+00:00")


def test_emitir_sin_admin_403(monkeypatch):
    svc = MagicMock()
    svc.emit_handover.side_effect = PermissionError("requiere owner/admin")
    client = make_client(monkeypatch, svc=svc)
    r = client.post("/v2/continuity/handover", json={"org_id": "o1", "project": "p"})
    assert r.status_code == 403


def test_emitir_proyecto_desconocido_404(monkeypatch):
    svc = MagicMock()
    svc.emit_handover.side_effect = ValueError("proyecto no encontrado")
    client = make_client(monkeypatch, svc=svc)
    r = client.post("/v2/continuity/handover", json={"org_id": "o1", "project": "p"})
    assert r.status_code == 404


def test_emitir_sin_clave_503(monkeypatch):
    svc = MagicMock()
    svc.emit_handover.side_effect = SigningKeyMissing("sin clave")
    client = make_client(monkeypatch, svc=svc)
    r = client.post("/v2/continuity/handover", json={"org_id": "o1", "project": "p"})
    assert r.status_code == 503


def test_latest_feliz_y_404(monkeypatch):
    svc = MagicMock()
    svc.latest_handover.return_value = {"share": "blob", "score": 50}
    client = make_client(monkeypatch, svc=svc)
    r = client.get("/v2/continuity/handover/latest",
                   params={"org_id": "o1", "project": "p"})
    assert r.status_code == 200 and r.json()["share"] == "blob"
    svc.latest_handover.return_value = None
    r = client.get("/v2/continuity/handover/latest",
                   params={"org_id": "o1", "project": "p"})
    assert r.status_code == 404
