"""Interruptor de LLM externo por organización (auditoría 23-nov, #17): endpoints
admin-only, repositorio y efecto real sobre las funciones de IA de la org."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.llm import org_policy
from src.llm.guard import ExternalLLMGuard
from src.orgs import llm_settings_api
from src.orgs.llm_settings import OrgLlmSettingsRepository
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(repo):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[llm_settings_api.get_llm_settings_repo] = lambda: repo
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_cache():
    org_policy.invalidate_policy_cache()
    yield
    org_policy.invalidate_policy_cache()


# --- endpoints -------------------------------------------------------------

def test_get_devuelve_el_ajuste():
    repo = MagicMock()
    repo.get_settings.return_value = {"org_id": "o1", "allow_external_llm": True}
    r = _client(repo).get("/v2/orgs/o1/llm-settings")
    assert r.status_code == 200
    assert r.json()["allow_external_llm"] is True
    repo.get_settings.assert_called_once_with(user_id="user-1", org_id="o1")


def test_put_desactiva_e_invalida_la_cache():
    repo = MagicMock()
    repo.set_settings.return_value = {"org_id": "o1", "allow_external_llm": False}
    org_policy._cache["o1"] = (True, 10 ** 12)
    r = _client(repo).put("/v2/orgs/o1/llm-settings", json={"allow_external_llm": False})
    assert r.status_code == 200 and r.json()["allow_external_llm"] is False
    repo.set_settings.assert_called_once_with(user_id="user-1", org_id="o1",
                                              allow_external_llm=False)
    assert "o1" not in org_policy._cache


@pytest.mark.parametrize("method, kwargs", [
    ("get", {}), ("put", {"json": {"allow_external_llm": False}})])
def test_no_admin_403(method, kwargs):
    repo = MagicMock()
    repo.get_settings.side_effect = PermissionError("owner/admin")
    repo.set_settings.side_effect = PermissionError("owner/admin")
    r = getattr(_client(repo), method)("/v2/orgs/o1/llm-settings", **kwargs)
    assert r.status_code == 403


def test_put_valida_el_cuerpo():
    r = _client(MagicMock()).put("/v2/orgs/o1/llm-settings", json={"allow_external_llm": "quizá"})
    assert r.status_code == 422


def test_requiere_sesion():
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[llm_settings_api.get_llm_settings_repo] = lambda: MagicMock()
    assert TestClient(app).get("/v2/orgs/o1/llm-settings").status_code == 401


def test_sin_multitenant_503():
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    assert TestClient(app).get("/v2/orgs/o1/llm-settings").status_code == 503


# --- repositorio -------------------------------------------------------------

class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class _Conn:
    def __init__(self, cur):
        self.cur = cur
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def _repo(rows):
    cur = _Cursor(rows)
    conn = _Conn(cur)
    repo = OrgLlmSettingsRepository()
    repo._connect = lambda: conn
    return repo, cur, conn


def test_repo_sin_fila_aplica_el_valor_por_defecto():
    repo, _, _ = _repo([None])
    assert repo.allows_external_llm("o1") is True


def test_repo_lee_el_ajuste():
    repo, _, _ = _repo([{"allow_external_llm": False}])
    assert repo.allows_external_llm("o1") is False


def test_repo_set_exige_admin():
    repo, cur, conn = _repo([{"ok": False}])
    with pytest.raises(PermissionError):
        repo.set_settings(user_id="u", org_id="o1", allow_external_llm=False)
    assert len(cur.executed) == 1 and not conn.committed


def test_repo_set_hace_upsert():
    repo, cur, conn = _repo([{"ok": True}])
    out = repo.set_settings(user_id="u", org_id="o1", allow_external_llm=False)
    assert out == {"org_id": "o1", "allow_external_llm": False}
    assert "on conflict (org_id)" in cur.executed[1][0] and conn.committed


def test_repo_get_exige_admin():
    repo, _, _ = _repo([{"ok": False}])
    with pytest.raises(PermissionError):
        repo.get_settings(user_id="u", org_id="o1")


def test_repo_org_of_solo_tablas_conocidas():
    repo, cur, _ = _repo([{"org_id": "o9"}])
    assert repo.org_of("test_runs", "r1") == "o9"
    with pytest.raises(ValueError):
        repo.org_of("memberships; drop table x", "r1")


# --- efecto en las funciones de IA -------------------------------------------

class _Recorder:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return '{"answer": "respuesta", "citations": []}'


def _ask_client(monkeypatch, guard):
    repo = MagicMock()
    repo.search_families_semantic.return_value = [
        {"family_id": "fam1", "title": "checkout 500", "label": "real",
         "occurrence_count": 3, "root_cause": "500"}]
    emb = MagicMock()
    emb.embed.return_value = [0.0] * 384
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    app.dependency_overrides[api_v2.get_embedder] = lambda: emb
    monkeypatch.setattr(api_v2, "get_llm_provider", lambda: guard)
    return TestClient(app)


def test_org_desactivada_degrada_como_sin_llm(monkeypatch):
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: org != "o-off")
    r = _ask_client(monkeypatch, guard).post(
        "/v2/defects/ask", json={"org_id": "o-off", "question": "¿qué rompe checkout?"})
    assert r.status_code == 200
    assert inner.prompts == []            # nada salió al proveedor externo


def test_org_activada_usa_el_llm_y_sale_saneado(monkeypatch):
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: org != "o-off")
    r = _ask_client(monkeypatch, guard).post(
        "/v2/defects/ask", json={"org_id": "o-on", "question": "mi DNI es 12345678Z, ¿qué rompe?"})
    assert r.status_code == 200
    assert len(inner.prompts) == 1 and "12345678Z" not in inner.prompts[0]


def test_ambito_por_run_usa_la_org_real_del_run(monkeypatch):
    """Con solo el run_id, el ámbito se resuelve con la org del run en la BD (no con
    un parámetro de la petición)."""
    monkeypatch.setattr("src.config.multi_tenant_enabled", lambda: True)
    looked_up = []

    def _org_of(self, table, row_id):
        looked_up.append((table, row_id))
        return "o-off"

    monkeypatch.setattr(OrgLlmSettingsRepository, "org_of", _org_of)
    inner = _Recorder()
    guard = ExternalLLMGuard(inner, policy=lambda org: org != "o-off")
    narrator = api_v2.LLMNarrator(guard)
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {
        "run": {"id": "r1"}, "summary": {"total": 1, "passed": 0, "failed": 1},
        "families": []}
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    app.dependency_overrides[api_v2.get_narrator] = lambda: narrator
    r = TestClient(app).get("/v2/assurance/run/r1?org_id=o-on")
    assert r.status_code == 200 and r.json()["narrative"] is None
    assert inner.prompts == [] and looked_up == [("test_runs", "r1")]


def test_migracion_035_idempotente_y_con_rls():
    sql = (Path(__file__).resolve().parent.parent / "db" / "migrations"
           / "035_org_llm_settings.sql").read_text()
    assert "create table if not exists public.org_llm_settings" in sql
    assert "enable row level security" in sql and "force row level security" in sql
    assert "is_org_member(org_id)" in sql and "is_org_admin(org_id)" in sql
