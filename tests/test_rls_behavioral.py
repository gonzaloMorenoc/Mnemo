import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def two_orgs():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user_b = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s,%s,'authenticated','authenticated',now(),now())",
                        (user_b, f"rls-{user_b[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("rls-A-" + user_b[:8], user_b))   # created_by no implica que user_b sea miembro de A
            org_a = str(cur.fetchone()[0])
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("rls-B-" + user_b[:8], user_b))
            org_b = str(cur.fetchone()[0])
            # user_b es miembro SOLO de B; sacarlo de A si el trigger de created_by lo añadió
            cur.execute("delete from public.memberships where org_id=%s and user_id=%s", (org_a, user_b))
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                        " on conflict (org_id, user_id) do update set role='member'", (org_b, user_b))
            # una familia de defectos en CADA org (seed con el rol del pooler = bypass)
            for org, sig in ((org_a, "sig-A"), (org_b, "sig-B")):
                cur.execute("insert into public.defect_families (org_id, scope, signature, title)"
                            " values (%s,'org',%s,%s)", (org, sig, "t-" + sig))
        conn.commit()
    yield {"user_b": user_b, "org_a": org_a, "org_b": org_b}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id in (%s,%s)", (org_a, org_b))
            cur.execute("delete from auth.users where id=%s", (user_b,))
        conn.commit()


def _count_families_as(user_id, org_id):
    """Cuenta familias de una org BAJO EL ROL authenticated + el claim del usuario (RLS activa)."""
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("set role authenticated")
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")
            cur.execute("select count(*) from public.defect_families where org_id = %s", (org_id,))
            n = cur.fetchone()[0]
            cur.execute("reset role")
            return n


def test_member_of_b_cannot_read_org_a_rows(two_orgs):
    ctx = two_orgs
    # control positivo: user_b SÍ ve su org B
    assert _count_families_as(ctx["user_b"], ctx["org_b"]) >= 1
    # aislamiento: user_b NO ve la org A a nivel de policy Postgres
    assert _count_families_as(ctx["user_b"], ctx["org_a"]) == 0
