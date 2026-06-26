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
def org():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"dedup-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("dedup-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def test_same_run_uid_dedups_without_error(org):
    repo = AssuranceRepository(DBURL)
    ruid = "run-" + uuid.uuid4().hex
    args = dict(user_id=org["user_id"], org_id=org["org_id"], project="web",
                source="playwright", commit_sha="sha1", run_uid=ruid,
                items=[], results=[], snapshots=[])
    first = repo.ingest_ci_run(**args)
    second = repo.ingest_ci_run(**args)   # misma entrega — NO debe lanzar UniqueViolation
    assert second["deduplicated"] is True
    assert second["run_id"] == first["run_id"]
