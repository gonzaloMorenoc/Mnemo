"""API /v2/projects: listar (miembro), crear/renombrar/archivar (owner/admin), validación."""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.projects.api as projects_api
from src.orgs.access import OrgAccess, get_org_access
from src.projects.repository import ProjectExists
from src.security import AuthenticatedUser, get_current_user

ORG, USER = "org-1", "user-1"
PID = "6f1c2e8a-0000-4000-8000-0000000000aa"
ROW = {"id": PID, "key": "web", "name": "Web", "description": None, "is_example": False,
       "archived": False, "created_at": "2026-11-23T00:00:00", "last_run_at": None,
       "runs": 0, "knowledge": 0}


class _Role:
    def __init__(self, role):
        self.role = role

    def role_of(self, *, org_id, user_id):
        return self.role if (org_id, user_id) == (ORG, USER) else None

    def org_of(self, *, resource, resource_id):
        return ORG


def _client(role):
    app = FastAPI()
    app.include_router(projects_api.router)
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        user_id=USER, email="u@x.com", claims={})
    app.dependency_overrides[get_org_access] = lambda: OrgAccess(_Role(role))
    repo = MagicMock()
    repo.list.return_value = [ROW]
    repo.create.return_value = ROW
    repo.update.return_value = {**ROW, "name": "Web nueva"}
    app.dependency_overrides[projects_api.get_project_repo] = lambda: repo
    return TestClient(app, raise_server_exceptions=False), repo


def test_un_viewer_lista_los_proyectos():
    client, repo = _client("viewer")
    resp = client.get(f"/v2/projects?org_id={ORG}")
    assert resp.status_code == 200 and resp.json() == [ROW]
    assert repo.list.call_args.kwargs == {"user_id": USER, "org_id": ORG, "include_archived": True}


def test_quien_no_es_miembro_no_lista():
    client, repo = _client(None)
    assert client.get(f"/v2/projects?org_id={ORG}").status_code == 403
    repo.list.assert_not_called()


@pytest.mark.parametrize("role", ["viewer", "member"])
def test_crear_y_editar_es_de_admin(role):
    client, repo = _client(role)
    assert client.post("/v2/projects", json={"org_id": ORG, "key": "web"}).status_code == 403
    assert client.patch(f"/v2/projects/{PID}", json={"name": "x"}).status_code == 403
    repo.create.assert_not_called()
    repo.update.assert_not_called()


def test_admin_crea_con_el_nombre_por_defecto_igual_a_la_clave():
    client, repo = _client("admin")
    resp = client.post("/v2/projects", json={"org_id": ORG, "key": "  web  "})
    assert resp.status_code == 201
    assert repo.create.call_args.kwargs == {"org_id": ORG, "key": "web", "name": "web",
                                            "description": None}


def test_clave_repetida_409():
    client, repo = _client("owner")
    repo.create.side_effect = ProjectExists("web")
    assert client.post("/v2/projects", json={"org_id": ORG, "key": "web"}).status_code == 409


@pytest.mark.parametrize("body", [
    {"org_id": ORG, "key": "con\nsalto"},
    {"org_id": ORG, "key": "   "},
    {"org_id": ORG, "key": "x" * 201},
    {"org_id": ORG, "key": "web", "name": "nombre\x1b[2J"},
])
def test_validacion_de_clave_y_nombre(body):
    client, repo = _client("admin")
    assert client.post("/v2/projects", json=body).status_code == 422
    repo.create.assert_not_called()


def test_patch_solo_nombre_descripcion_y_archivado():
    client, repo = _client("admin")
    resp = client.patch(f"/v2/projects/{PID}", json={"name": "Web nueva", "archived": True,
                                                    "key": "otra"})
    assert resp.status_code == 200 and resp.json()["name"] == "Web nueva"
    assert repo.update.call_args.kwargs == {"project_id": PID, "name": "Web nueva",
                                            "description": None, "archived": True}


def test_patch_de_un_id_raro_o_inexistente_es_404():
    client, repo = _client("admin")
    assert client.patch("/v2/projects/no-uuid", json={"name": "x"}).status_code == 404
    repo.update.return_value = None
    assert client.patch(f"/v2/projects/{PID}", json={"name": "x"}).status_code == 404
