"""Tokens de lectura + servidor MCP contra un Postgres de PRUEBA (nunca producción).

MNEMO_TEST_DATABASE_URL, no DATABASE_URL (en local es producción). Cubre la migración
037 (ámbitos, caducidad, FK de proyecto), la búsqueda de fallos y el criterio de
«hecho» del plan: un token de solo lectura de un proyecto ve la razón y la lección de
su test que falla, y no puede escribir ni ver otro proyecto.
"""
import os
import uuid
from contextlib import contextmanager

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from src.ci.ingest_tokens import (READ_TOKEN_PREFIX, SCOPE_READ, IngestTokenRepository,
                                  UnknownProject)
from src.continuity.repository import ContinuityRepository
from src.defects.fingerprint import fingerprint
from src.ingest.models import FailureRecord
from src.mcp_server import server
from src.mcp_server.lookup import FailureLookup
from src.mcp_server.tools import MemoryTools
from src.memory.repository import FamilyMemoryRepository
from src.projects.repository import ProjectRepository

pytestmark = [pytest.mark.integration, pytest.mark.testdb]
DBURL = os.getenv("MNEMO_TEST_DATABASE_URL", "")


@contextmanager
def _conn():
    with psycopg.connect(DBURL, row_factory=dict_row) as conn:
        yield conn


class _TestPool:
    def connection(self):
        return _conn()


@pytest.fixture
def pool(monkeypatch):
    import src.ci.ingest_tokens as tokens
    import src.continuity.index as index
    import src.continuity.repository as continuity_repo
    for module in (tokens, index, continuity_repo):
        monkeypatch.setattr(module, "get_pool", lambda: _TestPool())


@pytest.fixture
def org(pool):
    if not DBURL:
        pytest.skip("MNEMO_TEST_DATABASE_URL no configurada")
    owner = str(uuid.uuid4())
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email) values (%s, 'o@t.local')", (owner,))
        cur.execute("insert into public.profiles (user_id, display_name) values (%s, 'María')",
                    (owner,))
        cur.execute("insert into public.organizations (name, created_by) values ('M', %s)"
                    " returning id::text as id", (owner,))
        org_id = cur.fetchone()["id"]
        cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'owner')"
                    " on conflict do nothing", (org_id, owner))
        fams = {}
        for proj, test in (("checkout", "test_pago_tarjeta"), ("banca", "test_login_banca")):
            cur.execute("insert into public.test_runs (org_id, project, source) values (%s,%s,"
                        "'junit') returning id", (org_id, proj))
            run = cur.fetchone()["id"]
            cur.execute("insert into public.defect_families (scope, org_id, signature, title, label)"
                        " values ('org', %s, %s, %s, 'infra') returning id::text as id",
                        (org_id, f"sig-{proj}-{org_id[:6]}", f"Fallo {proj}"))
            fams[proj] = cur.fetchone()["id"]
            rec = FailureRecord(test_name=test, error_type="TimeoutError",
                                message="pasarela 504", trace=None, project=proj, source="junit")
            cur.execute("insert into public.failures (run_id, org_id, test_name, error_type, message,"
                        " fingerprint, defect_family_id) values (%s,%s,%s,'TimeoutError',"
                        "'pasarela 504',%s,%s)", (run, org_id, test, fingerprint(rec), fams[proj]))
            cur.execute("insert into public.triage_corrections (org_id, family_id, human_category,"
                        " reason, corrected_by) values (%s,%s,'infra',%s,%s)",
                        (org_id, fams[proj], f"El sandbox de {proj} se cae los lunes", owner))
            cur.execute("insert into public.qa_knowledge (org_id, kind, title, approach, project,"
                        " defect_family_id, created_by) values (%s,'leccion',%s,'reintentar',%s,%s,%s)",
                        (org_id, f"Lección {proj}", proj, fams[proj], owner))
        conn.commit()
    yield {"org": org_id, "owner": owner, "fams": fams}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id = %s", (org_id,))
        cur.execute("delete from auth.users where id = %s", (owner,))
        conn.commit()


def _tokens():
    return IngestTokenRepository(db_url="postgres://test")


def _read_token(org, **kw):
    return _tokens().create_token(user_id=org["owner"], org_id=org["org"], name="claude",
                                  scope=SCOPE_READ, **kw)


# -- tokens ------------------------------------------------------------------------

def test_los_tokens_viejos_quedan_de_ingesta(org):
    out = _tokens().create_token(user_id=org["owner"], org_id=org["org"], name="ci")
    assert out["scope"] == "ingest"
    assert _tokens().resolve(token=out["token"])["org_id"] == org["org"]
    assert _tokens().resolve(token=out["token"], scope=SCOPE_READ) is None


def test_token_de_lectura_no_vale_para_ingerir(org):
    out = _read_token(org, project="checkout")
    assert out["token"].startswith(READ_TOKEN_PREFIX)
    assert _tokens().resolve(token=out["token"]) is None           # /ci/ingest lo rechaza
    info = _tokens().resolve(token=out["token"], scope=SCOPE_READ)
    assert info["project"] == "checkout" and info["acting_user_id"] == org["owner"]


def test_caducado_y_revocado_no_resuelven(org):
    out = _read_token(org, expires_in_days=1)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("update public.ingest_tokens set expires_at = now() - interval '1 second'"
                    " where id = %s", (out["id"],))
        conn.commit()
    assert _tokens().resolve(token=out["token"], scope=SCOPE_READ) is None
    other = _read_token(org)
    assert _tokens().revoke_token(user_id=org["owner"], token_id=other["id"])
    assert _tokens().resolve(token=other["token"], scope=SCOPE_READ) is None


def test_proyecto_inexistente_y_lista_por_ambito(org):
    with pytest.raises(UnknownProject):
        _read_token(org, project="no-existe")
    _read_token(org)
    _tokens().create_token(user_id=org["owner"], org_id=org["org"], name="ci")
    listed = _tokens().list_tokens(user_id=org["owner"], org_id=org["org"], scope="read")
    assert [t["scope"] for t in listed] == ["read"]
    assert "token_hash" not in listed[0] and "token" not in listed[0]


def test_la_bd_rechaza_ambitos_desconocidos(org):
    with _conn() as conn, conn.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("insert into public.ingest_tokens (org_id, name, token_hash, created_by, scopes)"
                    " values (%s,'x','h-x',%s,'{admin}')", (org["org"], org["owner"]))


# -- búsqueda de fallos y alcance por proyecto ----------------------------------------

def test_lookup_por_huella_y_por_nombre(org):
    lookup = FailureLookup(connection_factory=_conn)
    exact = lookup.find(org_id=org["org"], test_name="test_pago_tarjeta",
                        message="pasarela 504", error_type="TimeoutError")
    assert exact[0] == {"family_id": org["fams"]["checkout"], "match": "huella"}
    partial = lookup.find(org_id=org["org"], test_name="PAGO_tar")
    assert partial == [{"family_id": org["fams"]["checkout"], "match": "nombre"}]
    assert lookup.find(org_id=org["org"], test_name="test_pago_tarjeta", project="banca") == []
    # Los comodines de LIKE se buscan literalmente.
    assert lookup.find(org_id=org["org"], test_name="%") == []


def _client(org):
    tools = MemoryTools(
        project_repo=ProjectRepository(connection_factory=_conn), knowledge_service=None,
        assurance_repo=None, memory_repo=FamilyMemoryRepository(connection_factory=_conn),
        lookup=FailureLookup(connection_factory=_conn), embedder=None,
        compute_index=__import__("src.continuity.index", fromlist=["x"]).compute_index,
        latest_act=ContinuityRepository().latest_act)
    app = FastAPI()
    app.include_router(server.router)
    return tools, app


def _call(client, token, name, args):
    res = client.post("/mcp", headers={"Authorization": f"Bearer {token}"},
                      json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": args}})
    assert res.status_code == 200, res.text
    return res.json()["result"]


def test_hecho_cuando_del_plan(org, monkeypatch):
    """Token de solo lectura de «checkout»: ve razón y lección de su test; nada más."""
    tools, app = _client(org)
    monkeypatch.setattr(server, "get_tools", lambda: tools)
    monkeypatch.setattr(server, "get_token_repo", _tokens)
    token = _read_token(org, project="checkout")["token"]
    client = TestClient(app)

    mine = _call(client, token, "get_failure_memory", {"test_name": "test_pago_tarjeta"})
    fam = mine["structuredContent"]["familias"][0]
    assert fam["reason"] == "El sandbox de checkout se cae los lunes"
    assert [lesson["title"] for lesson in fam["lessons"]] == ["Lección checkout"]
    assert fam["projects"] == ["checkout"]

    # Otro proyecto: ni pidiéndolo ni buscando su test.
    other = _call(client, token, "get_failure_memory",
                  {"test_name": "test_login_banca", "project": "banca"})
    assert other["isError"] and "checkout" in other["content"][0]["text"]
    hidden = _call(client, token, "get_failure_memory", {"test_name": "test_login_banca"})
    assert hidden["structuredContent"]["familias"] == []
    listed = _call(client, token, "list_projects", {})
    assert [p["key"] for p in listed["structuredContent"]["proyectos"]] == ["checkout"]
    overview = _call(client, token, "get_project_overview", {})
    assert overview["structuredContent"]["proyecto"] == "checkout"

    # Escribir: no hay herramientas de escritura y el token no vale para ingerir.
    names = {t["name"] for t in client.post(
        "/mcp", headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]}
    assert names == {"list_projects", "search_memory", "get_failure_memory",
                     "get_project_overview"}
    assert _tokens().resolve(token=token) is None


def test_familia_compartida_no_filtra_texto_de_otro_proyecto(org, monkeypatch):
    """Revisión: el mismo fallo en checkout y banca es UNA familia; la razón la escribió
    alguien de banca. El token de checkout ve la etiqueta y sus lecciones, no esa razón."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("insert into public.defect_families (scope, org_id, signature, title, label)"
                    " values ('org', %s, %s, 'mensaje de banca', 'infra') returning id::text as id",
                    (org["org"], f"sig-shared-{org['org'][:6]}"))
        fam = cur.fetchone()["id"]
        for proj in ("checkout", "banca"):
            cur.execute("select id from public.test_runs where org_id=%s and project=%s limit 1",
                        (org["org"], proj))
            cur.execute("insert into public.failures (run_id, org_id, test_name, message,"
                        " fingerprint, defect_family_id) values (%s,%s,'test_login_comun','x',"
                        "'fp-shared',%s)", (cur.fetchone()["id"], org["org"], fam))
        cur.execute("insert into public.triage_corrections (org_id, family_id, human_category,"
                    " reason, corrected_by) values (%s,%s,'infra','el sandbox del cliente X',%s)",
                    (org["org"], fam, org["owner"]))
        conn.commit()
    tools, app = _client(org)
    monkeypatch.setattr(server, "get_tools", lambda: tools)
    monkeypatch.setattr(server, "get_token_repo", _tokens)
    client = TestClient(app)

    scoped = _call(client, _read_token(org, project="checkout")["token"], "get_failure_memory",
                   {"test_name": "test_login_comun"})["structuredContent"]["familias"][0]
    assert scoped["compartida"] and scoped["label"] == "infra"
    assert "reason" not in scoped and "title" not in scoped
    assert "cliente X" not in str(scoped) and "banca" not in str(scoped)

    whole = _call(client, _read_token(org)["token"], "get_failure_memory",
                  {"test_name": "test_login_comun"})["structuredContent"]["familias"][0]
    assert whole["reason"] == "el sandbox del cliente X"
    assert sorted(whole["projects"]) == ["banca", "checkout"]

    lookup = FailureLookup(connection_factory=_conn)
    assert lookup.shared_with_other_projects(org_id=org["org"], family_ids=[fam, org["fams"]["checkout"]],
                                             project="checkout") == {fam}
    # Por debajo de 3 caracteres, solo nombre exacto.
    assert lookup.find(org_id=org["org"], test_name="lo") == []
