"""Proyecto como entidad contra un Postgres de PRUEBA con todas las migraciones.

MNEMO_TEST_DATABASE_URL (nunca DATABASE_URL, que en local es producción). El CI lo
corre en el job «Migraciones y BD». Cubre la migración 036 (trigger + FK), el
repositorio y el filtro por proyecto de la búsqueda con vectores reales.
"""
import os
import uuid
from contextlib import contextmanager

import psycopg
import pytest
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.defects.repository import AssuranceRepository
from src.knowledge.repository import QaKnowledgeRepository
from src.projects.repository import ProjectExists, ProjectRepository

pytestmark = [pytest.mark.integration, pytest.mark.testdb]
DBURL = os.getenv("MNEMO_TEST_DATABASE_URL", "")
DIM = 384


@contextmanager
def _conn():
    with psycopg.connect(DBURL) as conn:
        yield conn


def _vec(axis: int, tilt: float = 0.0) -> Vector:
    v = [0.0] * DIM
    v[axis] = 1.0
    v[(axis + 1) % DIM] = tilt
    return Vector(v)


@pytest.fixture
def org():
    if not DBURL:
        pytest.skip("MNEMO_TEST_DATABASE_URL no configurada")
    user, outsider = str(uuid.uuid4()), str(uuid.uuid4())
    with _conn() as conn, conn.cursor() as cur:
        register_vector(conn)
        for u in (user, outsider):
            cur.execute("insert into auth.users (id, email) values (%s, %s)", (u, f"{u[:8]}@t.local"))
        cur.execute("insert into public.organizations (name, created_by) values ('P', %s) returning id",
                    (user,))
        org_id = str(cur.fetchone()[0])
        cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'owner')"
                    " on conflict do nothing", (org_id, user))
        conn.commit()
    yield {"org": org_id, "user": user, "outsider": outsider}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id = %s", (org_id,))
        cur.execute("delete from auth.users where id = any(%s::uuid[])", ([user, outsider],))
        conn.commit()


def _repo():
    return ProjectRepository(connection_factory=_conn)


class _TestPool:
    """Sustituye al pool de la app (que lee DATABASE_URL) por la BD de PRUEBA."""

    @contextmanager
    def connection(self):
        with psycopg.connect(DBURL, row_factory=dict_row) as conn:
            register_vector(conn)
            yield conn


@pytest.fixture
def test_pool(monkeypatch):
    import src.defects.repository as defects_repo
    import src.knowledge.repository as knowledge_repo
    for module in (defects_repo, knowledge_repo):
        monkeypatch.setattr(module, "get_pool", lambda: _TestPool())


def _keys(org):
    return [p["key"] for p in _repo().list(user_id=org["user"], org_id=org["org"])]


# ── Migración 036 ───────────────────────────────────────────────────────────────

def test_una_ingesta_crea_el_proyecto_sola_y_los_null_no(org):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("insert into public.test_runs (org_id, project, source) values (%s,'web','junit')",
                    (org["org"],))
        cur.execute("insert into public.test_runs (org_id, project, source) values (%s,'web','junit')",
                    (org["org"],))
        cur.execute("insert into public.qa_knowledge (org_id, kind, title, project, created_by)"
                    " values (%s,'leccion','general',null,%s)", (org["org"], org["user"]))
        conn.commit()
    assert _keys(org) == ["web"]


def test_la_fk_impide_proyectos_huerfanos(org):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("alter table public.test_runs disable trigger ensure_project")
        try:
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                cur.execute("insert into public.test_runs (org_id, project, source)"
                            " values (%s,'sin-fila','junit')", (org["org"],))
        finally:
            conn.rollback()


# ── Repositorio ─────────────────────────────────────────────────────────────────

def test_crear_listar_renombrar_y_archivar(org):
    repo = _repo()
    created = repo.create(org_id=org["org"], key="banca-movil", name="Banca móvil",
                          description="App de clientes")
    assert created["key"] == "banca-movil" and created["name"] == "Banca móvil"
    with pytest.raises(ProjectExists):
        repo.create(org_id=org["org"], key="banca-movil", name="otra", description=None)
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("insert into public.test_runs (org_id, project, source)"
                    " values (%s,'banca-movil','junit')", (org["org"],))
        conn.commit()
    updated = repo.update(project_id=created["id"], name="Banca Móvil 2", archived=True)
    assert updated["name"] == "Banca Móvil 2" and updated["archived"] is True
    assert updated["key"] == "banca-movil" and updated["runs"] == 1
    assert repo.list(user_id=org["user"], org_id=org["org"], include_archived=False) == []
    again = repo.update(project_id=created["id"], archived=False)
    assert again["archived"] is False
    assert repo.update(project_id=str(uuid.uuid4()), name="x") is None


def test_quien_no_es_miembro_no_lista_nada(org):
    _repo().create(org_id=org["org"], key="web", name="Web", description=None)
    assert _repo().list(user_id=org["outsider"], org_id=org["org"]) == []


# ── Filtro por proyecto en la búsqueda ──────────────────────────────────────────

def test_busqueda_de_conocimiento_por_proyecto(org, test_pool):
    with _conn() as conn:
        register_vector(conn)
        cur = conn.cursor()
        for title, project in (("de A", "A"), ("de B", "B"), ("de toda la org", None)):
            cur.execute("insert into public.qa_knowledge (org_id, kind, title, project, created_by,"
                        " embedding) values (%s,'leccion',%s,%s,%s,%s)",
                        (org["org"], title, project, org["user"], _vec(0)))
        conn.commit()
    repo = QaKnowledgeRepository(db_url=DBURL, embedder=object())
    titles = lambda project: sorted(r["title"] for r in repo.search_semantic(  # noqa: E731
        user_id=org["user"], org_id=org["org"], query_embedding=_vec(0).to_list(), k=10,
        project=project))
    assert titles("A") == ["de A", "de toda la org"]
    assert titles(None) == ["de A", "de B", "de toda la org"]


def test_busqueda_de_familias_por_proyecto(org, test_pool):
    with _conn() as conn:
        register_vector(conn)
        cur = conn.cursor()
        fams = {}
        for name in ("fa", "fb"):
            cur.execute("insert into public.defect_families (scope, org_id, signature, title, centroid)"
                        " values ('org',%s,%s,%s,%s) returning id",
                        (org["org"], f"sig-{name}-{org['org'][:6]}", name, _vec(5)))
            fams[name] = cur.fetchone()[0]
        for name, project in (("fa", "A"), ("fb", "B")):
            cur.execute("insert into public.test_runs (org_id, project, source) values (%s,%s,'junit')"
                        " returning id", (org["org"], project))
            run = cur.fetchone()[0]
            cur.execute("insert into public.failures (run_id, org_id, test_name, message, fingerprint,"
                        " defect_family_id) values (%s,%s,'t','m','fp',%s)", (run, org["org"], fams[name]))
        conn.commit()
    repo = AssuranceRepository(db_url=DBURL)
    titles = lambda project: sorted(r["title"] for r in repo.search_families_semantic(  # noqa: E731
        user_id=org["user"], org_id=org["org"], query_embedding=_vec(5).to_list(), k=10,
        project=project))
    assert titles("A") == ["fa"]
    assert titles(None) == ["fa", "fb"]


def test_conocimiento_con_proyecto_vacio_es_de_toda_la_org(org):
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("insert into public.qa_knowledge (org_id, kind, title, project, created_by)"
                    " values (%s,'leccion','t','   ',%s) returning project", (org["org"], org["user"]))
        assert cur.fetchone()[0] is None
        conn.commit()
    assert _keys(org) == []
