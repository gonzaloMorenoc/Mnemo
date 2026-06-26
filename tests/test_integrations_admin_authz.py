import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.jira.integrations_repository import IntegrationsRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def org_with_member():
    """owner (auto-enrolado por trigger) + un segundo usuario con role 'member'."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    owner = str(uuid.uuid4())
    member = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            for uid in (owner, member):
                cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                            " values (%s,%s,'authenticated','authenticated',now(),now())",
                            (uid, f"u-{uid[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("authz-org-" + owner[:8], owner))
            org_id = str(cur.fetchone()[0])
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                        " on conflict (org_id, user_id) do update set role='member'", (org_id, member))
        conn.commit()
    yield {"owner": owner, "member": member, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id = any(%s)", ([owner, member],))
        conn.commit()


def test_member_cannot_reconfigure_github(org_with_member):
    repo = IntegrationsRepository(DBURL)
    ctx = org_with_member
    with pytest.raises(PermissionError):
        repo.upsert_github_config(user_id=ctx["member"], org_id=ctx["org_id"],
                                  installation_id="123", repo_full_name="o/r")


def test_owner_can_reconfigure_github(org_with_member):
    repo = IntegrationsRepository(DBURL)
    ctx = org_with_member
    repo.upsert_github_config(user_id=ctx["owner"], org_id=ctx["org_id"],
                              installation_id="123", repo_full_name="o/r")
    cfg = repo.get_github_config(user_id=ctx["owner"], org_id=ctx["org_id"])
    assert cfg["configured"] is True and cfg["repo_full_name"] == "o/r"


def test_member_cannot_reconfigure_jira(org_with_member):
    repo = IntegrationsRepository(DBURL)
    ctx = org_with_member
    with pytest.raises(PermissionError):
        repo.upsert_jira_config(user_id=ctx["member"], org_id=ctx["org_id"],
                                base_url="https://x.atlassian.net", email="a@b.c",
                                token="t", jql="project=X")
