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
            # dos familias con centroide: una "cerca" del vector de consulta, otra lejos
            near = [1.0] + [0.0] * 383
            far = [0.0] * 383 + [1.0]
            cur.execute("insert into public.defect_families (org_id, scope, signature, title, centroid, label, occurrence_count)"
                        " values (%s,'org',%s,%s,%s,'real',3)",
                        (org, "sig-near", "checkout 500", Vector(near)))
            cur.execute("insert into public.defect_families (org_id, scope, signature, title, centroid, label, occurrence_count)"
                        " values (%s,'org',%s,%s,%s,'flaky',1)",
                        (org, "sig-far", "login timeout", Vector(far)))
        conn.commit()
    yield {"user": user, "org": org, "near": near}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_semantic_search_orders_by_similarity(org_with_families):
    repo = AssuranceRepository(DBURL)
    ctx = org_with_families
    res = repo.search_families_semantic(user_id=ctx["user"], org_id=ctx["org"], query_embedding=ctx["near"], k=8)
    assert len(res) == 2
    assert res[0]["title"] == "checkout 500"   # la más cercana primero
    assert res[0]["family_id"] and res[0]["label"] == "real"
    assert res[1]["title"] == "login timeout"  # la lejana segunda


def test_semantic_search_empty_for_non_member(org_with_families):
    repo = AssuranceRepository(DBURL)
    other = str(uuid.uuid4())
    assert repo.search_families_semantic(user_id=other, org_id=org_with_families["org"],
                                         query_embedding=org_with_families["near"], k=8) == []
