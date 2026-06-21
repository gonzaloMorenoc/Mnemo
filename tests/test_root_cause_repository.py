import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

import psycopg  # noqa: E402

from src.defects.repository import AssuranceRepository, IngestItem  # noqa: E402
from src.ingest.models import FailureRecord  # noqa: E402
from src.defects.fingerprint import fingerprint  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org():
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"rc-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s, %s) returning id",
                        ("rc-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def _ingest_one(repo, u, o):
    rec = FailureRecord(test_name="t", error_type="TimeoutException", message="boom 30000ms",
                        trace="at A.java:1", project="proj-a", source="allure")
    item = IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=[0.1] * 384)
    repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure", items=[item])
    return repo.list_defects(user_id=u, org_id=o)[0]["id"]


def test_get_family_with_failures_and_save_root_cause(repo, org):
    u, o = org["user_id"], org["org_id"]
    fid = _ingest_one(repo, u, o)
    data = repo.get_family_with_failures(user_id=u, defect_id=fid)
    assert data is not None
    assert data["family"]["root_cause"] is None
    assert data["failures"] and data["failures"][0]["message"] == "boom 30000ms"
    assert repo.save_root_cause(user_id=u, defect_id=fid, text="## Causa raíz\nx") is True
    data2 = repo.get_family_with_failures(user_id=u, defect_id=fid)
    assert data2["family"]["root_cause"] == "## Causa raíz\nx"


def test_non_member_cannot_read_or_write(repo, org):
    u, o = org["user_id"], org["org_id"]
    fid = _ingest_one(repo, u, o)
    other = str(uuid.uuid4())
    assert repo.get_family_with_failures(user_id=other, defect_id=fid) is None
    assert repo.save_root_cause(user_id=other, defect_id=fid, text="x") is False
