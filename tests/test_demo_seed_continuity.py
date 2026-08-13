"""La siembra del escenario: añade lo que falta y NADA más (idempotencia).

Integration: org desechable contra la BD real, cleanup total.
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.continuity.index import compute_index  # noqa: E402
from src.demo.seed_continuity import seed_continuity  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.integration


@pytest.fixture()
def org_demo_desechable():
    """Una org llamada 'Demo MTP' (el seed la localiza por nombre+created_by) con
    un run de checkout-suite para que el proyecto exista."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"seedc-{user[:8]}@test.internal"))
        cur.execute("insert into public.organizations (name, created_by)"
                    " values ('Demo MTP',%s) returning id", (user,))
        org = str(cur.fetchone()[0])
        cur.execute("insert into public.test_runs (org_id, project, source)"
                    " values (%s,'checkout-suite','junit')", (org,))
        conn.commit()
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_primera_siembra_crea_los_nueve_y_sube_el_oficio(org_demo_desechable):
    user = org_demo_desechable["user"]
    out = seed_continuity(db_url=DBURL, demo_user_id=user)
    assert out["created"] == 9 and out["skipped"] == 0

    idx = compute_index(user_id=user, org_id=org_demo_desechable["org"],
                        project="checkout-suite")
    dims = {d["key"]: d for d in idx["dimensions"]}
    assert (dims["oficio"]["num"], dims["oficio"]["den"]) == (4, 4)


def test_segunda_siembra_no_crea_nada_ni_mueve_el_indice(org_demo_desechable):
    user = org_demo_desechable["user"]
    seed_continuity(db_url=DBURL, demo_user_id=user)
    antes = compute_index(user_id=user, org_id=org_demo_desechable["org"],
                          project="checkout-suite")

    out2 = seed_continuity(db_url=DBURL, demo_user_id=user)

    assert out2["created"] == 0 and out2["skipped"] == 9
    despues = compute_index(user_id=user, org_id=org_demo_desechable["org"],
                            project="checkout-suite")
    assert despues == antes  # la idempotencia es lo que hace seguro correrlo en prod


def test_sin_org_demo_se_salta_con_motivo():
    out = seed_continuity(db_url=DBURL, demo_user_id=str(uuid.uuid4()))
    assert out.get("skipped") is True and "Demo MTP" in out["reason"]
