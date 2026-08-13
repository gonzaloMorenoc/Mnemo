"""Continuidad: repositorio de actas y servicio de emisión (auditoría 12-ago, paso 3).

Los tests del repositorio son integration (BD real, fixtures propios con cleanup);
los del servicio son unit con claves Ed25519 generadas al vuelo.
"""
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.continuity.repository import ContinuityRepository  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture()
def org_con_admin():
    """Org nueva con un usuario owner. Cleanup total al salir (esto es la BD real)."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"cont-{user[:8]}@test.internal"))
        # El trigger create_owner_membership ya da de alta al creador como owner:
        # insertarla a mano viola memberships_pkey.
        cur.execute("insert into public.organizations (name, created_by)"
                    " values (%s,%s) returning id", ("cont-org-" + user[:8], user))
        org = str(cur.fetchone()[0])
        conn.commit()
    yield {"org": org, "user": user}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where id=%s", (org,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


@pytest.mark.integration
def test_save_y_latest_devuelven_el_acta_mas_reciente(org_con_admin):
    repo = ContinuityRepository()
    org, user = org_con_admin["org"], org_con_admin["user"]
    for score in (10, 42):  # dos actas: latest debe ser la segunda
        assert repo.save_act(
            user_id=user, org_id=org, project="checkout-suite",
            canonical_json={"schema": "mnemo.traspaso.v1", "score": score},
            signature="firma==", score=score, created_by=user) is not None
    act = repo.latest_act(user_id=user, org_id=org, project="checkout-suite")
    assert act["score"] == 42
    assert act["canonical_json"]["schema"] == "mnemo.traspaso.v1"
    assert act["signature"] == "firma=="
    assert isinstance(act["created_at"], str) and "T" in act["created_at"]


@pytest.mark.integration
def test_latest_sin_actas_es_none(org_con_admin):
    repo = ContinuityRepository()
    assert repo.latest_act(user_id=org_con_admin["user"],
                           org_id=org_con_admin["org"], project="nada") is None


@pytest.mark.integration
def test_no_miembro_no_guarda_ni_lee(org_con_admin):
    repo = ContinuityRepository()
    extrano = str(uuid.uuid4())
    assert repo.save_act(user_id=extrano, org_id=org_con_admin["org"],
                         project="p", canonical_json={}, signature="s",
                         score=1, created_by=extrano) is None
    assert repo.latest_act(user_id=extrano, org_id=org_con_admin["org"],
                           project="p") is None


@pytest.mark.integration
def test_is_org_admin_distingue_roles(org_con_admin):
    repo = ContinuityRepository()
    org = org_con_admin["org"]
    assert repo.is_org_admin(user_id=org_con_admin["user"], org_id=org) is True
    assert repo.is_org_admin(user_id=str(uuid.uuid4()), org_id=org) is False
