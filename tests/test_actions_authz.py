import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.actions.repository import ActionRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def org_member_and_admin():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    admin = str(uuid.uuid4())
    member = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            for u, em in ((admin, "adm"), (member, "mem")):
                cur.execute(
                    "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (u, f"{em}-{u[:8]}@test.internal"),
                )
            # created_by triggers create_owner_membership → admin becomes 'owner'
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s,%s) returning id",
                ("authz-org-" + admin[:8], admin),
            )
            org = str(cur.fetchone()[0])
            # Force admin role explicitly (owner also satisfies owner/admin check)
            cur.execute(
                "insert into public.memberships (org_id, user_id, role) values (%s,%s,'admin')"
                " on conflict (org_id, user_id) do update set role='admin'",
                (org, admin),
            )
            # Add member with role 'member' (must NOT be able to write)
            cur.execute(
                "insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                " on conflict (org_id, user_id) do update set role='member'",
                (org, member),
            )
            # Seed full chain: test_run → failure → triage_verdict → action
            cur.execute(
                "insert into public.test_runs (org_id, project, source) values (%s,'p','playwright') returning id",
                (org,),
            )
            run = str(cur.fetchone()[0])
            cur.execute(
                "insert into public.failures (org_id, run_id, test_name, error_type, message, fingerprint)"
                " values (%s,%s,'t','E','m','fp-authz-'||%s) returning id",
                (org, run, admin[:8]),
            )
            fid = str(cur.fetchone()[0])
            cur.execute(
                "insert into public.triage_verdicts"
                " (failure_id, run_id, org_id, category, confidence, rule_applied,"
                "  requires_approval, llm_assisted, status, evidence_bundle)"
                " values (%s,%s,%s,'real',0.9,'R1',false,false,'resolved','{}') returning id",
                (fid, run, org),
            )
            vid = str(cur.fetchone()[0])
            cur.execute(
                "insert into public.actions (triage_verdict_id, run_id, org_id, kind, summary, status)"
                " values (%s,%s,%s,'ticket','authz-test','proposed') returning id",
                (vid, run, org),
            )
            act = str(cur.fetchone()[0])
        conn.commit()
    yield {"admin": admin, "member": member, "org": org, "action": act}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id in (%s,%s)", (admin, member))
        conn.commit()


def test_member_cannot_approve_admin_can(org_member_and_admin):
    repo = ActionRepository(DBURL)
    ctx = org_member_and_admin
    assert repo.approve_action(user_id=ctx["member"], action_id=ctx["action"]) is False  # member: no
    assert repo.approve_action(user_id=ctx["admin"], action_id=ctx["action"]) is True    # admin: sí


def test_member_cannot_reject(org_member_and_admin):
    repo = ActionRepository(DBURL)
    ctx = org_member_and_admin
    assert repo.reject_action(user_id=ctx["member"], action_id=ctx["action"], reason="x") is False


def test_member_cannot_mark_materializing(org_member_and_admin):
    # admin aprueba; luego un member intenta reclamar la materialización → no
    repo = ActionRepository(DBURL)
    ctx = org_member_and_admin
    assert repo.approve_action(user_id=ctx["admin"], action_id=ctx["action"]) is True
    assert repo.mark_materializing(user_id=ctx["member"], action_id=ctx["action"]) is False
    assert repo.mark_materializing(user_id=ctx["admin"], action_id=ctx["action"]) is True
