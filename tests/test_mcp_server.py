"""Servidor MCP (/mcp): protocolo, autenticación, límite, Origin y herramientas, sin BD."""
from types import SimpleNamespace

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp_server import server
from src.mcp_server.ratelimit import TokenBucket
from src.mcp_server.tools import (NOTICE, MemoryTools, TokenContext, ToolInputError, safe,
                                  scoped_project)

TOKEN = "mnemo_rt_" + "a" * 48
INFO = {"token_id": "t1", "org_id": "o1", "acting_user_id": "u1", "project": None}


class _Tokens:
    def __init__(self, info=INFO, error=None):
        self.info, self.error, self.calls = info, error, []

    def resolve(self, *, token, scope):
        self.calls.append((token, scope))
        if self.error:
            raise self.error
        return self.info if token == TOKEN else None


class _Projects:
    def list(self, *, user_id, org_id, include_archived):
        return [{"key": "checkout", "name": "Checkout", "runs": 3, "token_hash": "x"},
                {"key": "banca", "name": "Banca", "runs": 1}]


class _Knowledge:
    def __init__(self):
        self.kwargs = None

    def search_unified(self, **kw):
        self.kwargs = kw
        return [{"id": "k1", "type": "knowledge", "title": "Lección",
                 "content": "token ghp_" + "b" * 36, "dist": 0.2, "score": 0.8}]


class _Memory:
    def __init__(self):
        self.kwargs = None

    def load(self, **kw):
        self.kwargs = kw
        return [SimpleNamespace(family_id=f, to_dict=lambda include_private, f=f: {
            "family_id": f, "reason": "razón", "reason_by_email": None})
            for f in kw["family_ids"]]


class _Lookup:
    def __init__(self, found):
        self.found, self.kwargs = found, None

    def find(self, **kw):
        self.kwargs = kw
        return self.found


class _Embedder:
    def embed(self, text):
        return [0.0]


class _Assurance:
    def search_families_semantic(self, **kw):
        return [{"family_id": "f-sem"}]


def _tools(found=(), **over):
    knowledge = _Knowledge()
    deps = dict(project_repo=_Projects(), knowledge_service=lambda: knowledge,
                assurance_repo=_Assurance(), memory_repo=_Memory(), lookup=_Lookup(list(found)),
                embedder=lambda: _Embedder(),
                compute_index=lambda **kw: {"score": 70, "dimensions": [], "inventario": {}},
                latest_act=lambda **kw: {"score": 65, "created_at": "2026-11-01T00:00:00"})
    deps.update(over)
    return MemoryTools(**deps), knowledge


@pytest.fixture
def client(monkeypatch):
    tokens = _Tokens()
    tools, _ = _tools()
    monkeypatch.setattr(server, "get_token_repo", lambda: tokens)
    monkeypatch.setattr(server, "get_tools", lambda: tools)
    monkeypatch.setattr(server, "_bucket", TokenBucket(per_minute=600, burst=50))
    app = FastAPI()
    app.include_router(server.router)
    c = TestClient(app)
    c.tokens = tokens
    return c


def _post(client, body, token=TOKEN, **headers):
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/mcp", json=body, headers=headers)


def _rpc(method, params=None, msg_id=1):
    msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


# -- transporte y protocolo -----------------------------------------------------------

def test_sin_token_401_con_www_authenticate(client):
    res = _post(client, _rpc("initialize"), token=None)
    assert res.status_code == 401
    assert res.headers["WWW-Authenticate"].startswith("Bearer")
    assert client.tokens.calls == [("", "read")]


def test_token_de_otro_ambito_o_falso_401(client):
    assert _post(client, _rpc("ping"), token="mnemo_it_" + "a" * 48).status_code == 401


def test_bd_caida_502(client, monkeypatch):
    monkeypatch.setattr(server, "get_token_repo",
                        lambda: _Tokens(error=psycopg.OperationalError("x")))
    assert _post(client, _rpc("ping")).status_code == 502


def test_org_sin_admin_403(client, monkeypatch):
    monkeypatch.setattr(server, "get_token_repo",
                        lambda: _Tokens(info={**INFO, "acting_user_id": None}))
    assert _post(client, _rpc("ping")).status_code == 403


def test_origin_ajeno_se_rechaza_antes_del_token(client):
    res = _post(client, _rpc("ping"), Origin="https://evil.example")
    assert res.status_code == 403 and client.tokens.calls == []


def test_origin_permitido(client, monkeypatch):
    monkeypatch.setattr(server, "MCP_ALLOWED_ORIGINS", frozenset({"https://app.example"}))
    assert _post(client, _rpc("ping"), Origin="https://app.example/").status_code == 200


def test_initialize_negocia_version(client):
    res = _post(client, _rpc("initialize", {"protocolVersion": "2025-03-26"})).json()["result"]
    assert res["protocolVersion"] == "2025-03-26"
    assert res["capabilities"] == {"tools": {"listChanged": False}}
    assert "instrucciones" in res["instructions"]
    unknown = _post(client, _rpc("initialize", {"protocolVersion": "1999-01-01"})).json()
    assert unknown["result"]["protocolVersion"] == server.SUPPORTED_VERSIONS[0]


def test_notificacion_202_sin_cuerpo(client):
    res = _post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert res.status_code == 202 and res.content == b""


def test_json_roto_y_lotes(client):
    bad = client.post("/mcp", content=b"{no", headers={"Authorization": f"Bearer {TOKEN}"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == server.PARSE_ERROR
    batch = _post(client, [_rpc("ping")])
    assert batch.status_code == 400 and batch.json()["error"]["code"] == server.INVALID_REQUEST


def test_metodo_desconocido(client):
    res = _post(client, _rpc("resources/list")).json()
    assert res["error"]["code"] == server.METHOD_NOT_FOUND


def test_get_y_delete_405(client):
    assert client.get("/mcp").status_code == 405
    assert client.delete("/mcp").status_code == 405


def test_tools_list_solo_lectura(client):
    tools = _post(client, _rpc("tools/list")).json()["result"]["tools"]
    assert {t["name"] for t in tools} == {"list_projects", "search_memory",
                                          "get_failure_memory", "get_project_overview"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)


def test_tools_call_ok_lleva_aviso_y_json(client):
    res = _post(client, _rpc("tools/call", {"name": "list_projects", "arguments": {}}))
    result = res.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["aviso"] == NOTICE
    assert "Checkout" in result["content"][0]["text"]
    # Solo campos públicos: nada que no esté en la lista blanca.
    assert "token_hash" not in result["content"][0]["text"]


def test_tools_call_error_de_entrada_y_fallo_interno(client, monkeypatch):
    res = _post(client, _rpc("tools/call", {"name": "search_memory", "arguments": {}})).json()
    assert res["result"]["isError"] and "query" in res["result"]["content"][0]["text"]

    class _Boom:
        def call(self, *a):
            raise RuntimeError("detalle interno")
    monkeypatch.setattr(server, "get_tools", lambda: _Boom())
    res = _post(client, _rpc("tools/call", {"name": "list_projects"})).json()
    assert res["result"]["isError"]
    assert "detalle interno" not in res["result"]["content"][0]["text"]


def test_tools_call_sin_nombre(client):
    res = _post(client, _rpc("tools/call", {"arguments": {}})).json()
    assert res["error"]["code"] == server.INVALID_PARAMS


def test_limite_por_token_429(client, monkeypatch):
    monkeypatch.setattr(server, "_bucket", TokenBucket(per_minute=60, burst=2))
    assert _post(client, _rpc("ping")).status_code == 200
    assert _post(client, _rpc("ping")).status_code == 200
    calls = len(client.tokens.calls)
    res = _post(client, _rpc("ping"))
    assert res.status_code == 429 and int(res.headers["Retry-After"]) >= 1
    assert len(client.tokens.calls) == calls        # ni siquiera se consultó la BD


# -- limitador -------------------------------------------------------------------------

def test_cubo_se_rellena_con_el_tiempo():
    now = [0.0]
    bucket = TokenBucket(per_minute=60, burst=1, clock=lambda: now[0])
    assert bucket.take("a") == 0
    assert bucket.take("a") == pytest.approx(1.0)
    assert bucket.take("b") == 0                       # cada token, su cubo
    now[0] = 1.0
    assert bucket.take("a") == 0


def test_cubo_acota_memoria(monkeypatch):
    import src.mcp_server.ratelimit as rl
    monkeypatch.setattr(rl, "MAX_BUCKETS", 2)
    now = [0.0]
    bucket = TokenBucket(per_minute=60, burst=1, clock=lambda: now[0])
    for key in ("a", "b", "c"):
        now[0] += 0.001
        bucket.take(key)
    assert set(bucket._buckets) == {"b", "c"}


# -- herramientas ------------------------------------------------------------------------

CTX = TokenContext(token_id="t1", org_id="o1", actor="u1")
CTX_P = TokenContext(token_id="t1", org_id="o1", actor="u1", project="checkout")


def test_el_proyecto_del_token_manda():
    assert scoped_project(CTX_P, {}, required=True) == "checkout"
    assert scoped_project(CTX_P, {"project": "checkout"}, required=True) == "checkout"
    with pytest.raises(ToolInputError, match="checkout"):
        scoped_project(CTX_P, {"project": "banca"}, required=False)
    assert scoped_project(CTX, {}, required=False) is None
    with pytest.raises(ToolInputError):
        scoped_project(CTX, {}, required=True)


def test_list_projects_filtra_por_token():
    tools, _ = _tools()
    out = tools.call(CTX_P, "list_projects", {})
    assert [p["key"] for p in out["proyectos"]] == ["checkout"]


def test_search_memory_sanea_y_pasa_el_proyecto():
    tools, knowledge = _tools()
    out = tools.call(CTX_P, "search_memory", {"query": "pagos", "limit": 3})
    assert knowledge.kwargs["project"] == "checkout" and knowledge.kwargs["k"] == 3
    assert "ghp_" not in out["fuentes"][0]["content"]
    assert "dist" not in out["fuentes"][0]


def test_argumentos_extra_o_mal_tipados():
    tools, _ = _tools()
    with pytest.raises(ToolInputError, match="no admitidos"):
        tools.call(CTX, "search_memory", {"query": "x", "org_id": "otra"})
    with pytest.raises(ToolInputError):
        tools.call(CTX, "search_memory", {"query": "x", "limit": True})
    with pytest.raises(ToolInputError):
        tools.call(CTX, "search_memory", {"query": "x" * 501})
    with pytest.raises(ToolInputError):
        tools.call(CTX, "nope", {})


def test_failure_memory_usa_huella_o_parecido():
    tools, _ = _tools(found=[{"family_id": "f1", "match": "huella"}])
    out = tools.call(CTX_P, "get_failure_memory", {"test_name": "t", "error_message": "m"})
    assert out["familias"][0]["coincidencia"] == "huella"
    assert tools.memory_repo.kwargs["project"] == "checkout"
    assert "reason_by_email" in out["familias"][0]   # to_dict(include_private=False) decide

    tools, _ = _tools(found=[])
    out = tools.call(CTX, "get_failure_memory", {"error_message": "pasarela 504"})
    assert out["familias"][0]["coincidencia"] == "parecido"

    tools, _ = _tools(found=[])
    out = tools.call(CTX, "get_failure_memory", {"test_name": "t"})   # sin mensaje: sin coseno
    assert out["familias"] == [] and out["nota"]
    with pytest.raises(ToolInputError):
        tools.call(CTX, "get_failure_memory", {})


def test_overview_valida_el_proyecto():
    tools, _ = _tools()
    out = tools.call(CTX, "get_project_overview", {"project": "banca"})
    assert out["indice_continuidad"]["score"] == 70 and out["ultima_acta"]["score"] == 65
    with pytest.raises(ToolInputError, match="no hay"):
        tools.call(CTX, "get_project_overview", {"project": "nada"})


def test_safe_quita_invisibles_y_recorta():
    text = safe("a‮b\x1bc " + "x" * 3000)
    assert "‮" not in text and "\x1b" not in text and len(text) <= 1200
    assert safe({"n": 1, "l": ["ok"]}) == {"n": 1, "l": ["ok"]}
