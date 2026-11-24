"""FamilyMemoryRepository contra un Postgres de PRUEBA (nunca producción).

Usa MNEMO_TEST_DATABASE_URL —no DATABASE_URL, que en local apunta a prod— con todas
las migraciones aplicadas (scripts/migrate.py). Sin la variable, se omite.
"""
import os
import uuid
from contextlib import contextmanager

import psycopg
import pytest

from src.memory.repository import FamilyMemoryRepository

pytestmark = [pytest.mark.integration, pytest.mark.testdb]
DBURL = os.getenv("MNEMO_TEST_DATABASE_URL", "")


@contextmanager
def _conn():
    with psycopg.connect(DBURL) as conn:
        yield conn


def _uid():
    return str(uuid.uuid4())


@pytest.fixture
def seeded():
    if not DBURL:
        pytest.skip("MNEMO_TEST_DATABASE_URL no configurada")
    maria, pablo, ajeno, ex = _uid(), _uid(), _uid(), _uid()
    with _conn() as conn, conn.cursor() as cur:
        for u in (maria, pablo, ajeno, ex):
            cur.execute("insert into auth.users (id, email) values (%s, %s)", (u, f"{u[:8]}@t.local"))
        cur.execute("insert into public.profiles (user_id, display_name) values (%s, 'María')", (maria,))
        cur.execute("insert into public.organizations (name, created_by) values ('A', %s) returning id",
                    (maria,))
        org = str(cur.fetchone()[0])
        cur.execute("insert into public.organizations (name, created_by) values ('B', %s) returning id",
                    (ajeno,))
        org_b = str(cur.fetchone()[0])
        for u, o in ((maria, org), (pablo, org), (ajeno, org_b)):
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                        " on conflict do nothing", (o, u))
        fams = {}
        for name, o in (("pago", org), ("login", org), ("sola", org), ("ajena", org_b)):
            cur.execute("insert into public.defect_families (scope, org_id, signature, title, label)"
                        " values ('org', %s, %s, %s, %s) returning id",
                        (o, f"sig-{name}-{org[:6]}", f"Error {name}",
                         "infra" if name == "pago" else "unknown"))
            fams[name] = str(cur.fetchone()[0])
        # pago: razón antigua de María, razón nueva de un ex miembro con un secreto dentro
        cur.execute("insert into public.triage_corrections (org_id, family_id, human_category, reason,"
                    " corrected_by, corrected_at) values (%s,%s,'infra','vieja',%s, now() - interval '2 days')",
                    (org, fams["pago"], maria))
        cur.execute("insert into public.triage_corrections (org_id, family_id, human_category, reason,"
                    " corrected_by) values (%s,%s,'infra',%s,%s)",
                    (org, fams["pago"], "Sandbox caído: 30 peticiones/minuto; token ghp_" + "a" * 36, ex))
        # la corrección MÁS reciente es de otra categoría: su razón no explica «infra»
        cur.execute("insert into public.triage_corrections (org_id, family_id, human_category, reason,"
                    " corrected_by, corrected_at) values (%s,%s,'flaky','era intermitente',%s,"
                    " now() + interval '1 minute')", (org, fams["pago"], pablo))
        # un contacto enlazado a la familia: datos de personas, no sale nunca
        cur.execute("insert into public.qa_knowledge (org_id, kind, title, approach, defect_family_id,"
                    " created_by) values (%s,'contacto','Laura (Pagos)','tel 600 000 000',%s,%s)",
                    (org, fams["login"], maria))
        # login: lecciones (una retirada) y dos runs en dos proyectos
        for title, status in (("Lección 1", "activo"), ("Lección 2", "activo"), ("Obsoleta", "obsoleto")):
            cur.execute("insert into public.qa_knowledge (org_id, kind, title, approach, defect_family_id,"
                        " created_by, status) values (%s,'leccion',%s,'hacer X',%s,%s,%s)",
                        (org, title, fams["login"], maria, status))
        runs = []
        for proj in ("web", "app", "web"):
            cur.execute("insert into public.test_runs (org_id, project, source) values (%s,%s,'junit')"
                        " returning id", (org, proj))
            runs.append(str(cur.fetchone()[0]))
        for run in runs:
            cur.execute("insert into public.failures (run_id, org_id, test_name, message, fingerprint,"
                        " defect_family_id) values (%s,%s,'t','m','fp',%s)", (run, org, fams["login"]))
        cur.execute("insert into public.failures (run_id, org_id, test_name, message, fingerprint,"
                    " defect_family_id) values (%s,%s,'t2','m','fp2',%s)", (runs[0], org, fams["pago"]))
        cur.execute("insert into public.failures (run_id, org_id, test_name, message, fingerprint,"
                    " defect_family_id) values (%s,%s,'t3','m','fp3',%s)", (runs[0], org, fams["login"]))
        conn.commit()
    yield {"org": org, "org_b": org_b, "maria": maria, "pablo": pablo, "ajeno": ajeno,
           "fams": fams, "runs": runs}
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id = any(%s::uuid[])", ([org, org_b],))
        cur.execute("delete from auth.users where id = any(%s::uuid[])", ([maria, pablo, ajeno, ex],))
        conn.commit()


def _repo():
    return FamilyMemoryRepository(connection_factory=_conn)


def test_carga_razon_mas_reciente_saneada_y_autor_ausente(seeded):
    f = seeded["fams"]
    [pago] = _repo().load(user_id=seeded["pablo"], org_id=seeded["org"], family_ids=[f["pago"]])
    assert pago.label == "infra"
    assert pago.reason.startswith("Sandbox caído: 30 peticiones/minuto;")   # no es una ruta
    assert "ghp_" not in pago.reason
    assert pago.reason_by is None              # el ex miembro no tiene perfil
    assert pago.reason_by_email.endswith("@t.local")   # solo para la app
    assert pago.reason_by_active is False
    assert "intermitente" not in pago.reason   # razón de otra etiqueta: no se cita


def test_lecciones_activas_y_estadisticas(seeded):
    f = seeded["fams"]
    [login] = _repo().load(user_id=seeded["pablo"], org_id=seeded["org"], family_ids=[f["login"]])
    assert sorted(lesson.title for lesson in login.lessons) == ["Lección 1", "Lección 2"]
    assert login.runs == 3
    assert login.projects == ("app", "web")
    assert login.has_memory


def test_respeta_el_orden_pedido_y_omite_desconocidas(seeded):
    f = seeded["fams"]
    out = _repo().load(user_id=seeded["pablo"], org_id=seeded["org"],
                       family_ids=[f["sola"], str(uuid.uuid4()), f["pago"], f["sola"]])
    assert [m.family_id for m in out] == [f["sola"], f["pago"]]
    assert not out[0].has_memory


def test_no_miembro_no_ve_nada(seeded):
    f = seeded["fams"]
    assert _repo().load(user_id=seeded["ajeno"], org_id=seeded["org"], family_ids=[f["pago"]]) == []


def test_nunca_mezcla_familias_de_otra_org(seeded):
    f = seeded["fams"]
    assert _repo().load(user_id=seeded["pablo"], org_id=seeded["org"], family_ids=[f["ajena"]]) == []


def test_familias_de_un_run_por_numero_de_fallos(seeded):
    f = seeded["fams"]
    org, ids = _repo().families_of_run(user_id=seeded["pablo"], run_id=seeded["runs"][0])
    assert org == seeded["org"]
    assert ids == [f["login"], f["pago"]]      # login aporta 2 fallos, pago 1
    assert _repo().families_of_run(user_id=seeded["ajeno"], run_id=seeded["runs"][0]) == (None, [])
    assert [m.family_id for m in _repo().for_run(user_id=seeded["pablo"],
                                                  run_id=seeded["runs"][0])] == ids


def test_org_de_una_familia(seeded):
    assert _repo().org_of_family(seeded["fams"]["pago"]) == seeded["org"]
    assert _repo().org_of_family(str(uuid.uuid4())) is None
