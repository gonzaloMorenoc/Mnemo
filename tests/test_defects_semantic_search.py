import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.defects.repository import AssuranceRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def org_with_families():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    from pgvector import Vector
    from pgvector.psycopg import register_vector
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s,%s,'authenticated','authenticated',now(),now())",
                        (user, f"nl-{user[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("nl-org-" + user[:8], user))
            org = str(cur.fetchone()[0])
            # dos familias con centroide: una "cerca" del vector de consulta, otra
            # ORTOGONAL (distancia coseno 1,0 — ruido puro, debe quedar cortada)
            near = [1.0] + [0.0] * 383
            far = [0.0] * 383 + [1.0]
            # cerca de la consulta (distancia ~0,04) pero sin empatar con `near`
            close = [1.0, 0.3] + [0.0] * 382
            cur.execute("insert into public.defect_families (org_id, scope, signature, title, centroid, label, occurrence_count)"
                        " values (%s,'org',%s,%s,%s,'real',3) returning id",
                        (org, "sig-near", "checkout 500", Vector(near)))
            near_id = str(cur.fetchone()[0])
            cur.execute("insert into public.defect_families (org_id, scope, signature, title, centroid, label, occurrence_count)"
                        " values (%s,'org',%s,%s,%s,'flaky',1)",
                        (org, "sig-far", "login timeout", Vector(far)))
            # dos correcciones humanas: la búsqueda debe devolver la razón MÁS RECIENTE
            cur.execute("insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, reason, corrected_by, corrected_at)"
                        " values (%s,%s,'flaky','real','razón antigua',%s, now() - interval '1 day')",
                        (org, near_id, user))
            cur.execute("insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, reason, corrected_by, corrected_at)"
                        " values (%s,%s,'flaky','real','Timeouts por runners fríos del sandbox del PSP',%s, now())",
                        (org, near_id, user))
            # Familia cuyos ERRORES quedan lejos de la consulta pero cuya RAZÓN humana
            # está cerca: el conocimiento del senior tiene que recuperarse igual.
            cur.execute("insert into public.defect_families (org_id, scope, signature, title, centroid, label, occurrence_count)"
                        " values (%s,'org',%s,%s,%s,'infra',2) returning id",
                        (org, "sig-reason", "socket hang up", Vector(far)))
            reason_id = str(cur.fetchone()[0])
            # Y al revés: errores que SÍ casan con la consulta (distancia 0,55) y una
            # razón que no (1,0). Media 0,775 > corte 0,75: la media sola la sacaría.
            partial = [0.45, 0.0, (1 - 0.45 ** 2) ** 0.5] + [0.0] * 381
            cur.execute("insert into public.defect_families (org_id, scope, signature, title, centroid, label, occurrence_count)"
                        " values (%s,'org',%s,%s,%s,'real',1) returning id",
                        (org, "sig-offreason", "pago duplicado", Vector(partial)))
            off_id = str(cur.fetchone()[0])
            cur.execute("insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, reason,"
                        "  reason_embedding, corrected_by)"
                        " values (%s,%s,'real','real','Confirmado por caja',%s,%s)",
                        (org, off_id, Vector(far), user))
            cur.execute("insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, reason,"
                        "  reason_embedding, corrected_by)"
                        " values (%s,%s,'real','infra','Sandbox del PSP en frío',%s,%s)",
                        (org, reason_id, Vector(close), user))
        conn.commit()
    yield {"user": user, "org": org, "near": near, "close": close}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_semantic_search_returns_relevant_and_cuts_noise(org_with_families):
    # Contrato nuevo (auditoría 12-ago, H2): la familia ortogonal (distancia 1,0)
    # queda CORTADA por MAX_SEMANTIC_DISTANCE en vez de colarse en el top-k.
    repo = AssuranceRepository(DBURL)
    ctx = org_with_families
    res = repo.search_families_semantic(user_id=ctx["user"], org_id=ctx["org"], query_embedding=ctx["near"], k=8)
    titles = [r["title"] for r in res]
    assert "login timeout" not in titles          # ruido puro: cortado
    assert titles[0] == "checkout 500"
    assert res[0]["family_id"] and res[0]["label"] == "real"


def test_semantic_search_exposes_latest_label_reason(org_with_families):
    # La razón del senior (última corrección) viaja con la familia (12-ago, H1).
    repo = AssuranceRepository(DBURL)
    ctx = org_with_families
    res = repo.search_families_semantic(user_id=ctx["user"], org_id=ctx["org"], query_embedding=ctx["near"], k=8)
    assert res[0]["label_reason"] == "Timeouts por runners fríos del sandbox del PSP"


def test_semantic_search_empty_for_non_member(org_with_families):
    repo = AssuranceRepository(DBURL)
    other = str(uuid.uuid4())
    assert repo.search_families_semantic(user_id=other, org_id=org_with_families["org"],
                                         query_embedding=org_with_families["near"], k=8) == []


def test_semantic_search_recovers_family_by_its_label_reason(org_with_families):
    # Los errores de "socket hang up" están a distancia 1,0 de la consulta, pero la
    # razón del etiquetador coincide: la familia entra por su razón (12-ago, H1).
    repo = AssuranceRepository(DBURL)
    ctx = org_with_families
    res = repo.search_families_semantic(user_id=ctx["user"], org_id=ctx["org"], query_embedding=ctx["near"], k=8)
    hit = [r for r in res if r["title"] == "socket hang up"]
    assert hit and hit[0]["label_reason"] == "Sandbox del PSP en frío"


def test_set_family_label_stores_reason_embedding(org_with_families):
    from pgvector.psycopg import register_vector
    repo = AssuranceRepository(DBURL)
    ctx = org_with_families
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select id from public.defect_families where org_id=%s and title='login timeout'",
                    (ctx["org"],))
        fam = str(cur.fetchone()[0])
    assert repo.set_family_label(user_id=ctx["user"], family_id=fam, label="flaky",
                                 reason="Runner frío", reason_embedding=ctx["close"])
    # Ahora "login timeout" también se recupera por su razón.
    res = repo.search_families_semantic(user_id=ctx["user"], org_id=ctx["org"], query_embedding=ctx["near"], k=8)
    assert "login timeout" in [r["title"] for r in res]
    with psycopg.connect(DBURL) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("select reason_embedding from public.triage_corrections"
                        " where family_id=%s order by corrected_at desc limit 1", (fam,))
            assert cur.fetchone()[0] is not None


def test_semantic_search_never_drops_what_the_errors_already_match(org_with_families):
    # Centroide a 0,55 (pasa el corte 0,75), razón a 1,0: media 0,775 (no lo pasa).
    # Sumar la razón no puede quitar resultados que antes existían.
    repo = AssuranceRepository(DBURL)
    ctx = org_with_families
    res = repo.search_families_semantic(user_id=ctx["user"], org_id=ctx["org"], query_embedding=ctx["near"], k=8)
    assert "pago duplicado" in [r["title"] for r in res]
