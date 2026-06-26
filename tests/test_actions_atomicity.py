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
def approved_action():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s,%s,'authenticated','authenticated',now(),now())",
                        (user, f"atom-{user[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("atom-org-" + user[:8], user))
            org = str(cur.fetchone()[0])
            cur.execute("insert into public.test_runs (org_id, project, source) values (%s,'web','playwright') returning id", (org,))
            run = str(cur.fetchone()[0])
            cur.execute("insert into public.failures (org_id, run_id, test_name, error_type, message, fingerprint)"
                        " values (%s,%s,'t','E','m','fp-'||%s) returning id", (org, run, user[:8]))
            fid = str(cur.fetchone()[0])
            cur.execute("insert into public.triage_verdicts (failure_id, run_id, org_id, category, confidence,"
                        " rule_applied, requires_approval, llm_assisted, status, evidence_bundle)"
                        " values (%s,%s,%s,'real',0.85,'R4_real_recurrent',false,false,'resolved','{}') returning id",
                        (fid, run, org))
            vid = str(cur.fetchone()[0])
            cur.execute("insert into public.actions (triage_verdict_id, run_id, org_id, kind, summary, status)"
                        " values (%s,%s,%s,'ticket','x','approved') returning id", (vid, run, org))
            aid = str(cur.fetchone()[0])
        conn.commit()
    yield {"user": user, "org": org, "action_id": aid}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_mark_materializing_is_a_single_winner(approved_action):
    repo = ActionRepository(DBURL)
    ctx = approved_action
    first = repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"])
    second = repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"])
    assert first is True and second is False   # solo el primero gana la transición


def test_materialize_only_from_materializing(approved_action):
    repo = ActionRepository(DBURL)
    ctx = approved_action
    # sin pasar por materializing, materialize_action (que ahora exige 'materializing') no aplica
    assert repo.materialize_action(user_id=ctx["user"], action_id=ctx["action_id"], artifact_ref="u") is False
    assert repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"]) is True
    assert repo.materialize_action(user_id=ctx["user"], action_id=ctx["action_id"], artifact_ref="u") is True


def test_revert_to_approved(approved_action):
    repo = ActionRepository(DBURL)
    ctx = approved_action
    assert repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"]) is True
    assert repo.revert_to_approved(user_id=ctx["user"], action_id=ctx["action_id"]) is True
    # tras revertir, se puede reclamar de nuevo
    assert repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"]) is True
