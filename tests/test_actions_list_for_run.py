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
def run_with_action():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s,%s,'authenticated','authenticated',now(),now())",
                        (user, f"br-{user[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("br-org-" + user[:8], user))
            org = str(cur.fetchone()[0])
            run = str(uuid.uuid4())
            cur.execute("insert into public.test_runs (id, org_id, project, source, summary)"
                        " values (%s,%s,'proj','playwright','{}')", (run, org))
            # Seed a failure (required by triage_verdicts FK)
            cur.execute(
                "insert into public.failures (run_id, org_id, test_name, message, fingerprint)"
                " values (%s,%s,'test_br','err','fp-br') returning id",
                (run, org))
            failure_id = str(cur.fetchone()[0])
            # Seed a triage_verdict (required by actions FK)
            cur.execute(
                "insert into public.triage_verdicts"
                " (failure_id, run_id, org_id, category, confidence, rule_applied)"
                " values (%s,%s,%s,'real',0.9,'R1') returning id",
                (failure_id, run, org))
            verdict_id = str(cur.fetchone()[0])
            cur.execute("insert into public.actions (org_id, run_id, triage_verdict_id, kind, payload, summary, status)"
                        " values (%s,%s,%s,'ticket','{}','Crear ticket','proposed')",
                        (org, run, verdict_id))
        conn.commit()
    yield {"user": user, "org": org, "run": run}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_list_actions_for_run_returns_run_actions(run_with_action):
    repo = ActionRepository(DBURL)
    ctx = run_with_action
    rows = repo.list_actions_for_run(user_id=ctx["user"], run_id=ctx["run"])
    assert len(rows) == 1 and rows[0]["kind"] == "ticket" and rows[0]["summary"] == "Crear ticket"


def test_list_actions_for_run_empty_for_non_member(run_with_action):
    repo = ActionRepository(DBURL)
    other = str(uuid.uuid4())
    assert repo.list_actions_for_run(user_id=other, run_id=run_with_action["run"]) == []
