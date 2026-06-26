import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()
DBURL = os.getenv("DATABASE_URL", "")


from src.defects.repository import AssuranceRepository
from src.certify.certificate import compute_self_eval


@pytest.fixture
def seeded_clean_run():
    """Org + user + run + one resolved triage_verdict (flaky). No triage_corrections → new tenant."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")

    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            # Auth user
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (user_id, f"selfeval-{user_id[:8]}@test.internal"),
            )
            # Org (trigger auto-creates membership for created_by user)
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("selfeval-org-" + user_id[:8], user_id),
            )
            org_id = str(cur.fetchone()[0])
            # Test run
            cur.execute(
                "insert into public.test_runs (org_id, project, source, commit_sha)"
                " values (%s, 'web', 'playwright', 'sha-selfeval') returning id",
                (org_id,),
            )
            run_id = str(cur.fetchone()[0])
            # Failure (required as FK for triage_verdict)
            cur.execute(
                "insert into public.failures"
                " (run_id, org_id, test_name, message, fingerprint)"
                " values (%s, %s, 'clean_test', 'flaky error', 'fp-selfeval') returning id",
                (run_id, org_id),
            )
            failure_id = str(cur.fetchone()[0])
            # Triage verdict: flaky, resolved — no triage_corrections for this org
            cur.execute(
                "insert into public.triage_verdicts"
                " (failure_id, run_id, org_id, category, confidence, rule_applied,"
                "  requires_approval, llm_assisted, status)"
                " values (%s, %s, %s, 'flaky', 0.85, 'R2_flaky_known',"
                "  false, false, 'resolved')",
                (failure_id, run_id, org_id),
            )
        conn.commit()

    yield {"user_id": user_id, "org_id": org_id, "run_id": run_id}

    # Teardown: cascade via org delete, then auth user
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def test_new_tenant_gets_low_confidence(seeded_clean_run):
    """Un tenant nuevo (sin triage_corrections) obtiene confidence='low' y n_corrections=0."""
    ctx = seeded_clean_run
    repo = AssuranceRepository(DBURL)

    raw = repo.get_calibration_metrics(user_id=ctx["user_id"], org_id=ctx["org_id"]) or {}
    cal = {
        "tenant_accuracy": raw.get("accuracy", 0.0),
        "n_corrections": raw.get("total", 0),
        "por_categoria_humana": raw.get("por_categoria", {}),
    }
    verdicts = repo.get_triage_for_run(user_id=ctx["user_id"], run_id=ctx["run_id"])
    se = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="2026-06-26T00:00:00Z")

    assert se["confidence"] == "low", f"expected 'low', got {se['confidence']!r}"
    assert se["engine_calibration"]["n_corrections"] == 0
