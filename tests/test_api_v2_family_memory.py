"""GET /v2/defects/{id}/memory: el panel «Memoria» del triaje (lectura, viewer incluido)."""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.memory.family_memory import FamilyMemory, Lesson
from src.orgs.access import OrgAccess, get_org_access
from src.security import AuthenticatedUser

ORG, USER = "org-1", "user-1"
FAM = "6f1c2e8a-0000-4000-8000-000000000001"

_MEM = FamilyMemory(family_id=FAM, title="TimeoutError", label="infra",
                    reason="El sandbox cae los lunes", reason_by="María",
                    lessons=(Lesson("k1", "leccion", "Espaciar la suite", "30 req/min"),),
                    projects=("web",), runs=3)


class _Role:
    def __init__(self, role):
        self.role = role

    def role_of(self, *, org_id, user_id):
        return self.role if (org_id, user_id) == (ORG, USER) else None

    def org_of(self, *, resource, resource_id):
        return ORG


class _Service:
    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def __call__(self, *args, **kwargs):
        return self

    def search_unified(self, **kwargs):
        self.calls.append(kwargs)
        return self.hits


def _client(role="viewer", memories=(_MEM,), org="org-1"):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id=USER, email="u@x.com", claims={})
    app.dependency_overrides[get_org_access] = lambda: OrgAccess(_Role(role))
    repo = MagicMock()
    repo.org_of_family.return_value = org
    repo.load.return_value = list(memories)
    app.dependency_overrides[api_v2.get_family_memory_repo] = lambda: repo
    for name in ("get_knowledge_repo", "get_assurance_repo", "get_embedder"):
        app.dependency_overrides[getattr(api_v2, name)] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False), repo


def test_viewer_ve_la_memoria_con_relacionados_sin_repetir_lecciones(monkeypatch):
    svc = _Service([{"id": "k1", "type": "knowledge", "title": "ya es lección"},
                    {"id": "fam9", "type": "defect", "title": "otra familia"},
                    {"id": "k2", "type": "knowledge", "title": "Runbook del PSP", "score": 0.8}])
    monkeypatch.setattr(api_v2, "KnowledgeService", svc)
    client, repo = _client()
    resp = client.get(f"/v2/defects/{FAM}/memory")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reason"] == "El sandbox cae los lunes" and body["label_text"]
    assert [lesson["title"] for lesson in body["lessons"]] == ["Espaciar la suite"]
    assert body["related"] == [{"id": "k2", "title": "Runbook del PSP", "score": 0.8}]
    assert repo.load.call_args.kwargs == {"user_id": USER, "org_id": ORG, "family_ids": [FAM]}
    assert "TimeoutError" in svc.calls[0]["query"] and "sandbox" in svc.calls[0]["query"]


def test_sin_relacionados_bajo_demanda(monkeypatch):
    svc = _Service([])
    monkeypatch.setattr(api_v2, "KnowledgeService", svc)
    client, _ = _client()
    assert client.get(f"/v2/defects/{FAM}/memory?related=false").json()["related"] == []
    assert svc.calls == []


def test_relacionados_fallan_y_el_panel_se_muestra_igual(monkeypatch):
    class _Boom(_Service):
        def search_unified(self, **kwargs):
            raise RuntimeError("sin modelo")
    monkeypatch.setattr(api_v2, "KnowledgeService", _Boom([]))
    client, _ = _client()
    resp = client.get(f"/v2/defects/{FAM}/memory")
    assert resp.status_code == 200 and resp.json()["related"] == []


def test_no_miembro_403():
    client, repo = _client(role=None)
    assert client.get(f"/v2/defects/{FAM}/memory").status_code == 403
    repo.load.assert_not_called()


def test_familia_inexistente_404():
    client, _ = _client(memories=())
    assert client.get(f"/v2/defects/{FAM}/memory?related=false").status_code == 404


def test_id_que_no_es_uuid_es_404_no_502():
    client, repo = _client()
    assert client.get("/v2/defects/no-es-uuid/memory").status_code == 404
    repo.org_of_family.assert_not_called()


def test_dentro_de_la_app_el_email_sirve_de_autor(monkeypatch):
    monkeypatch.setattr(api_v2, "KnowledgeService", _Service([]))
    mem = FamilyMemory(family_id=FAM, title="T", label="infra", reason="r",
                       reason_by=None, reason_by_email="maria@empresa.com")
    client, _ = _client(memories=(mem,))
    assert client.get(f"/v2/defects/{FAM}/memory").json()["reason_by_email"] == "maria@empresa.com"
