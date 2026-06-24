# tests/test_actions_repository.py
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.actions.repository import ActionRepository
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord

DBURL = os.getenv("DATABASE_URL", "")


def _emb(seed):
    return [seed] + [0.0] * 383


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def arepo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return ActionRepository(DBURL)


@pytest.fixture
def org(repo):
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"test-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def _resolved_verdict(repo, u, o):
    """Ingiere un run con un fallo real y persiste un veredicto 'resolved'; devuelve (run_id, verdict_id, fid)."""
    rec = FailureRecord(test_name="t_checkout", error_type="AssertionError", message="boom",
                        trace=None, project="web", source="playwright")
    item = IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(1.0))
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="web", source="playwright", run_uid="ra",
                           items=[item], results=[{"test_name": "t_checkout", "status": "fail"}], snapshots=[])
    fid = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["failure_id"]
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[{
        "failure_id": fid, "category": "real", "confidence": 0.85, "rule_applied": "R4_real_recurrent",
        "evidence_bundle": {"family_id": "x"}, "requires_approval": False, "llm_assisted": False,
        "status": "resolved"}])
    vid = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]["id"]
    return r["run_id"], vid, fid


def test_get_run_actionable_verdicts_joins_failure(repo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    rows = repo.get_run_actionable_verdicts(user_id=u, run_id=run_id)
    assert len(rows) == 1
    assert rows[0]["verdict_id"] == vid and rows[0]["test_name"] == "t_checkout"
    assert rows[0]["category"] == "real"
    # no-miembro → vacío
    assert repo.get_run_actionable_verdicts(user_id=str(uuid.uuid4()), run_id=run_id) == []


def test_save_approve_materialize_roundtrip(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    assert arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {"title": "T"}, "summary": "s"}]) == 1
    inbox = arepo.get_actions(user_id=u, org_id=o, status="proposed")
    assert len(inbox) == 1
    aid = inbox[0]["id"]
    # proposed → approved (sin ref)
    assert arepo.approve_action(user_id=u, action_id=aid) is True
    got = arepo.get_actions(user_id=u, org_id=o)[0]
    assert got["status"] == "approved" and got["approved_by"] == u and got["artifact_ref"] is None
    # approved → materialized (con ref)
    assert arepo.materialize_action(user_id=u, action_id=aid,
                                    artifact_ref="https://github.com/o/r/issues/1") is True
    got = arepo.get_actions(user_id=u, org_id=o)[0]
    assert got["status"] == "materialized" and got["artifact_ref"] == "https://github.com/o/r/issues/1"
    # materializar de nuevo → False (ya no está 'approved')
    assert arepo.materialize_action(user_id=u, action_id=aid, artifact_ref="x") is False


def test_get_action_includes_org_id(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s"}])
    aid = arepo.get_actions(user_id=u, org_id=o)[0]["id"]
    assert arepo.get_action(user_id=u, action_id=aid)["org_id"] == o


def test_save_actions_preserves_approved_on_reproposal(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s"}])
    aid = arepo.get_actions(user_id=u, org_id=o)[0]["id"]
    arepo.approve_action(user_id=u, action_id=aid)
    # re-proponer: la aprobada NO se borra
    arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s2"}])
    all_actions = arepo.get_actions(user_id=u, org_id=o)
    assert any(a["status"] == "approved" for a in all_actions)   # preservada
    assert any(a["status"] == "proposed" for a in all_actions)   # nueva propuesta


def test_save_actions_rejects_foreign_run(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    with pytest.raises((ValueError, PermissionError)):
        arepo.save_actions(user_id=u, org_id=o, run_id=str(uuid.uuid4()), actions=[])


def test_approve_action_non_member_returns_false(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s"}])
    aid = arepo.get_actions(user_id=u, org_id=o)[0]["id"]
    assert arepo.approve_action(user_id=str(uuid.uuid4()), action_id=aid) is False


def test_get_selfheal_context_returns_error_and_doms(repo, org):
    u, o = org["user_id"], org["org_id"]
    from src.defects.fingerprint import fingerprint
    from src.defects.repository import IngestItem
    from src.ingest.models import FailureRecord
    rec = FailureRecord(test_name="t_co", error_type="TimeoutError",
                        message="waiting for locator('#btn')", trace=None, project="web", source="playwright",
                        file="tests/co.spec.ts")
    item = IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=[1.0] + [0.0] * 383)
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="web", source="playwright", run_uid="sh",
                           commit_sha="c1", items=[item],
                           results=[{"test_name": "t_co", "status": "fail"}],
                           snapshots=[{"test_name": "t_co", "kind": "last_green", "content": "<button>Go</button>", "commit_sha": "c0"},
                                      {"test_name": "t_co", "kind": "failure", "content": "<button id='v2'>Go</button>", "commit_sha": "c1"}])
    fid = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["failure_id"]
    ctx = repo.get_selfheal_context(user_id=u, failure_id=fid)
    assert ctx is not None
    assert "locator('#btn')" in ctx["error_message"]
    assert ctx["green_dom"] == "<button>Go</button>" and "v2" in ctx["failure_dom"]
    assert ctx["file"] == "tests/co.spec.ts"
    import uuid as _uuid
    assert repo.get_selfheal_context(user_id=str(_uuid.uuid4()), failure_id=fid) is None
