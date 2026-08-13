"""La siembra de riqueza: semanal-idempotente, triaje solo de unknown, protegidos intactos."""
import os
import uuid
from datetime import date

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.demo.seed_riqueza import seed_riqueza, week_uids  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


def test_week_uids_deterministas_y_acotados():
    uids = week_uids("tienda-online", start=date(2026, 7, 23), until=date(2026, 8, 13))
    assert uids[0][0] == "riqueza-tienda-online-2026-W30"
    assert len(uids) == 4                       # W30..W33
    assert uids == week_uids("tienda-online", start=date(2026, 7, 23), until=date(2026, 8, 13))


def test_week_uids_no_fecha_en_el_futuro():
    # El run de la semana en curso se fecha como muy tarde en `until`, nunca después.
    uids = week_uids("api-pagos", start=date(2026, 8, 10), until=date(2026, 8, 11))
    assert all(fecha <= date(2026, 8, 11) for _, fecha in uids)


@pytest.fixture()
def org_riqueza():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"riq-{user[:8]}@test.internal"))
        cur.execute("insert into public.organizations (name, created_by)"
                    " values ('Demo MTP',%s) returning id", (user,))
        org = str(cur.fetchone()[0])
        conn.commit()
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


@pytest.mark.integration
def test_siembra_y_reejecucion_semanal(org_riqueza):
    """Primera pasada crea runs; la segunda con el MISMO tope no crea ninguno
    (dedup por run_uid); con tope una semana más tarde crea solo la semana nueva."""
    out1 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 13))
    assert out1["runs_creados"] > 0
    out2 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 13))
    assert out2["runs_creados"] == 0
    out3 = seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"],
                        until=date(2026, 8, 20))
    assert out3["runs_creados"] == 6            # una semana nueva × 6 proyectos


@pytest.mark.integration
def test_los_protegidos_no_ganan_fallos_ni_kb(org_riqueza):
    seed_riqueza(db_url=DBURL, demo_user_id=org_riqueza["user"], until=date(2026, 8, 13))
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from public.failures fl"
                    " join public.test_runs tr on tr.id=fl.run_id"
                    " where tr.org_id=%s and tr.project in ('checkout-suite','banca-movil')",
                    (org_riqueza["org"],))
        assert cur.fetchone()[0] == 0
        cur.execute("select count(*) from public.qa_knowledge"
                    " where org_id=%s and project in ('checkout-suite','banca-movil')",
                    (org_riqueza["org"],))
        assert cur.fetchone()[0] == 0
