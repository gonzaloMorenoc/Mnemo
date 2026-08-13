"""El índice de continuidad: determinista, por proyecto, con denominadores honestos.

Integration: corre contra la BD real con fixtures propios y cleanup total.
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.continuity.index import compute_index, list_projects  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.integration

PROJ = "cont-proj"


@pytest.fixture()
def org_poblada():
    """Org con: 3 familias del proyecto (2 recurrentes, 1 con lección y razón),
    1 familia de OTRO proyecto (no debe contar), conocimiento del oficio (2 de 4
    kinds), 2 reglas (1 respaldada por una lección de su dominio) y 1 item con
    project NULL (no debe contar)."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    ids = {}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"idx-{user[:8]}@test.internal"))
        # El trigger create_owner_membership da de alta al creador como owner.
        cur.execute("insert into public.organizations (name, created_by)"
                    " values (%s,%s) returning id", ("idx-org-" + user[:8], user))
        org = str(cur.fetchone()[0])

        def run(project):
            # source tiene CHECK con la lista de formatos soportados: 'junit' vale.
            cur.execute("insert into public.test_runs (org_id, project, source)"
                        " values (%s,%s,'junit') returning id", (org, project))
            return str(cur.fetchone()[0])

        def familia(occ, label="unknown"):
            # label es NOT NULL con default 'unknown' = «nadie la ha triado».
            cur.execute("insert into public.defect_families"
                        " (org_id, scope, signature, title, occurrence_count, label)"
                        " values (%s,'org',%s,%s,%s,%s) returning id",
                        (org, f"sig-{uuid.uuid4().hex[:8]}", "t", occ, label))
            return str(cur.fetchone()[0])

        def fallo(run_id, fam_id):
            cur.execute("insert into public.failures (run_id, org_id, defect_family_id,"
                        " test_name, message, fingerprint)"
                        " values (%s,%s,%s,'t','m',%s)",
                        (run_id, org, fam_id, uuid.uuid4().hex[:16]))

        r1, r_otro = run(PROJ), run("otro-proyecto")
        # fam_a: recurrente, etiquetada, con lección y con razón → suma en todo
        ids["fam_a"] = familia(3, label="real")
        # fam_b: recurrente, etiquetada, SIN lección y SIN razón
        ids["fam_b"] = familia(2, label="flaky")
        # fam_c: una sola ocurrencia (fuera de memoria_defectos) y SIN triar
        # (label 'unknown') → tampoco entra en el denominador de razon_etiquetas
        ids["fam_c"] = familia(1)
        # fam_otro: recurrente y etiquetada, pero de otro proyecto
        ids["fam_otro"] = familia(5, label="real")
        for f in ("fam_a", "fam_b", "fam_c"):
            fallo(r1, ids[f])
        fallo(r_otro, ids["fam_otro"])

        cur.execute("insert into public.triage_corrections (org_id, family_id,"
                    " engine_category, human_category, reason, corrected_by)"
                    " values (%s,%s,'flaky','real','timeouts por runners fríos',%s)",
                    (org, ids["fam_a"], user))

        def kn(kind, project, domain=None, fam=None):
            cur.execute("insert into public.qa_knowledge (org_id, kind, title, domain,"
                        " project, created_by, defect_family_id)"
                        " values (%s,%s,%s,%s,%s,%s,%s)",
                        (org, kind, f"{kind}-item", domain, project, user, fam))

        kn("leccion", PROJ, domain="pagos", fam=ids["fam_a"])  # respalda fam_a y el dominio pagos
        kn("runbook", PROJ)                                     # oficio 1/4
        kn("contacto", PROJ)                                    # oficio 2/4
        kn("regla_negocio", PROJ, domain="pagos")               # respaldada
        kn("riesgo", PROJ, domain="envios")                     # SIN respaldo
        kn("dato_prueba", None)                                 # project NULL: NO cuenta
        conn.commit()
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_dimensiones_con_numeradores_y_denominadores_exactos(org_poblada):
    idx = compute_index(user_id=org_poblada["user"], org_id=org_poblada["org"], project=PROJ)
    dims = {d["key"]: d for d in idx["dimensions"]}
    # 2 recurrentes del proyecto (a, b); solo a tiene conocimiento vinculado
    assert (dims["memoria_defectos"]["num"], dims["memoria_defectos"]["den"]) == (1, 2)
    # 2 etiquetadas (a, b); solo a tiene una corrección con razón
    assert (dims["razon_etiquetas"]["num"], dims["razon_etiquetas"]["den"]) == (1, 2)
    # runbook + contacto presentes → 2/4
    assert (dims["oficio"]["num"], dims["oficio"]["den"]) == (2, 4)
    # regla en pagos respaldada; riesgo en envios sin respaldo → 1/2
    assert (dims["reglas_respaldadas"]["num"], dims["reglas_respaldadas"]["den"]) == (1, 2)


def test_score_es_la_media_ponderada_redondeada(org_poblada):
    idx = compute_index(user_id=org_poblada["user"], org_id=org_poblada["org"], project=PROJ)
    # las cuatro dimensiones dan 0,5 → 0,35*0,5 + 0,25*0,5 + 0,25*0,5 + 0,15*0,5 = 0,5
    assert idx["score"] == 50


def test_otro_proyecto_renormaliza_las_dimensiones_sin_datos(org_poblada):
    """«otro-proyecto» tiene 1 familia recurrente etiquetada sin lección ni razón, y
    CERO conocimiento propio:
      memoria 0/1 (0,35) · razon 0/1 (0,25) · oficio 0/4 (0,25) · reglas den 0 (fuera)
    → renormaliza sobre 0,85 con todos los numeradores a 0 → score 0, no null."""
    idx = compute_index(user_id=org_poblada["user"], org_id=org_poblada["org"],
                        project="otro-proyecto")
    dims = {d["key"]: d for d in idx["dimensions"]}
    assert dims["memoria_defectos"]["den"] == 1      # solo fam_otro
    assert dims["oficio"]["num"] == 0                # su conocimiento es de PROJ
    assert dims["reglas_respaldadas"]["den"] == 0    # excluida y renormalizada
    assert idx["score"] == 0                          # honesto: no sabe nada


def test_inventario(org_poblada):
    idx = compute_index(user_id=org_poblada["user"], org_id=org_poblada["org"], project=PROJ)
    inv = idx["inventario"]
    assert inv["familias"] == 3
    assert inv["familias_con_leccion"] == 1
    assert inv["conocimiento_por_kind"]["runbook"] == 1
    assert inv["conocimiento_por_kind"]["dato_prueba"] == 0   # el de project NULL no cuenta
    assert inv["dominios"] == 2                                # pagos, envios
    assert (inv["etiquetas_con_razon"], inv["etiquetas"]) == (1, 2)


def test_no_miembro_none(org_poblada):
    assert compute_index(user_id=str(uuid.uuid4()), org_id=org_poblada["org"],
                         project=PROJ) is None


def test_list_projects_une_runs_y_conocimiento(org_poblada):
    projects = list_projects(user_id=org_poblada["user"], org_id=org_poblada["org"])
    assert projects == ["cont-proj", "otro-proyecto"]
