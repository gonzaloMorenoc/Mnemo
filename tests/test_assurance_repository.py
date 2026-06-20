import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from src.ingest.models import FailureRecord
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem

DBURL = os.getenv("DATABASE_URL", "")


def _emb(seed: float):
    return [seed] + [0.0] * 383


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org(repo):
    user_id = str(uuid.uuid4())
    email = f"test-{user_id[:8]}@test.internal"
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            # Create a real auth.users row so FK constraints are satisfied
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (user_id, email),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("test-org-" + user_id[:8], user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def _item(project, msg, trace, seed):
    rec = FailureRecord(
        test_name="t",
        error_type="TimeoutException",
        message=msg,
        trace=trace,
        project=project,
        source="allure",
    )
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_ingest_groups_same_error_across_projects(repo, org):
    u, o = org["user_id"], org["org_id"]
    r1 = repo.ingest_run(
        user_id=u,
        org_id=o,
        project="proj-a",
        source="allure",
        items=[_item("proj-a", "TimeoutException after 100ms", "at A.java:1", 1.0)],
    )
    r2 = repo.ingest_run(
        user_id=u,
        org_id=o,
        project="proj-b",
        source="allure",
        items=[_item("proj-b", "TimeoutException after 999ms", "at A.java:2", 1.0)],
    )
    assert r1["known"] == 0 and r1["novel"] == 1
    assert r2["known"] == 1 and r2["novel"] == 0
    defects = repo.list_defects(user_id=u, org_id=o)
    assert len(defects) == 1
    assert defects[0]["occurrence_count"] == 2
    lineage = repo.get_lineage(user_id=u, defect_id=defects[0]["id"])
    projects = {f["project"] for f in lineage["failures"]}
    assert projects == {"proj-a", "proj-b"}


def test_isolation_between_orgs(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.ingest_run(
        user_id=u,
        org_id=o,
        project="p",
        source="allure",
        items=[_item("p", "UniqueError xyz", None, 0.5)],
    )
    other_user = str(uuid.uuid4())
    assert repo.list_defects(user_id=other_user, org_id=o) == []


def test_ingest_run_rejects_non_member(repo, org):
    other_user = str(uuid.uuid4())
    with pytest.raises(PermissionError):
        repo.ingest_run(user_id=other_user, org_id=org["org_id"], project="p", source="allure",
                        items=[_item("p", "X", None, 0.3)])
