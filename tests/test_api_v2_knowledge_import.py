"""Tests de POST /v2/knowledge/import y POST /v2/knowledge/proposals/{id}/refine."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.knowledge.import_service import ImportNotConfigured, ImportRateLimited
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(import_svc=None, proposal_svc=None):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    if import_svc is not None:
        app.dependency_overrides[api_v2.get_knowledge_import_service] = lambda: import_svc
    if proposal_svc is not None:
        app.dependency_overrides[api_v2.get_knowledge_proposal_service] = lambda: proposal_svc
    return TestClient(app)


def test_import_feliz():
    svc = MagicMock()
    svc.import_refs.return_value = {"created": [{"id": "p1"}], "refreshed": [],
                                    "skipped": [], "errors": []}
    client = make_client(import_svc=svc)
    r = client.post("/v2/knowledge/import", json={"org_id": "o1", "refs": ["PAY-1"]})
    assert r.status_code == 200
    assert r.json()["created"][0]["id"] == "p1"
    svc.import_refs.assert_called_once_with(user_id="user-1", org_id="o1",
                                            refs=["PAY-1"])


def test_import_sin_integracion_409():
    svc = MagicMock()
    svc.import_refs.side_effect = ImportNotConfigured("configura la integración")
    client = make_client(import_svc=svc)
    r = client.post("/v2/knowledge/import", json={"org_id": "o1", "refs": ["PAY-1"]})
    assert r.status_code == 409


def test_import_tope_hora_429():
    svc = MagicMock()
    svc.import_refs.side_effect = ImportRateLimited("tope alcanzado")
    client = make_client(import_svc=svc)
    r = client.post("/v2/knowledge/import", json={"org_id": "o1", "refs": ["PAY-1"]})
    assert r.status_code == 429


def test_import_11_refs_422_por_pydantic():
    client = make_client(import_svc=MagicMock())
    r = client.post("/v2/knowledge/import",
                    json={"org_id": "o1", "refs": [f"PAY-{i}" for i in range(11)]})
    assert r.status_code == 422


def test_import_cero_refs_422():
    client = make_client(import_svc=MagicMock())
    r = client.post("/v2/knowledge/import", json={"org_id": "o1", "refs": []})
    assert r.status_code == 422


def test_refine_feliz():
    svc = MagicMock()
    svc.repo.get_proposal.return_value = {"id": "p1", "status": "pending"}
    svc.refine.return_value = {"id": "p1", "title": "Mejor"}
    client = make_client(proposal_svc=svc)
    r = client.post("/v2/knowledge/proposals/p1/refine")
    assert r.status_code == 200
    assert r.json()["title"] == "Mejor"


def test_refine_no_existe_404():
    svc = MagicMock()
    svc.repo.get_proposal.return_value = None
    client = make_client(proposal_svc=svc)
    r = client.post("/v2/knowledge/proposals/nope/refine")
    assert r.status_code == 404


def test_refine_llm_caido_503_y_propuesta_intacta():
    svc = MagicMock()
    svc.repo.get_proposal.return_value = {"id": "p1", "status": "pending"}
    svc.refine.return_value = None
    client = make_client(proposal_svc=svc)
    r = client.post("/v2/knowledge/proposals/p1/refine")
    assert r.status_code == 503
    assert "queda como estaba" in r.json()["detail"]
