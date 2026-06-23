import os
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord

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
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
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


def _item(test_name, msg, seed, error_type="TimeoutError"):
    rec = FailureRecord(test_name=test_name, error_type=error_type, message=msg,
                        trace=None, project="p", source="playwright")
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_get_triage_inputs_non_member(repo, org):
    out = repo.ingest_ci_run(user_id=org["user_id"], org_id=org["org_id"], project="p",
                             source="playwright", run_uid="r", items=[_item("t", "x", 1.0)],
                             results=[{"test_name": "t", "status": "fail"}], snapshots=[])
    other = str(uuid.uuid4())
    assert repo.get_triage_inputs(user_id=other, run_id=out["run_id"])["run"] is None


def test_is_novel_vs_recurrent(repo, org):
    u, o = org["user_id"], org["org_id"]
    # run 1: familia nueva
    r1 = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="n1",
                            items=[_item("t1", "TimeoutError boom", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out1 = repo.get_triage_inputs(user_id=u, run_id=r1["run_id"])
    assert out1["failures"][0]["is_novel"] is True
    # run 2: mismo error (misma familia) → ahora recurrente
    r2 = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="n2",
                            items=[_item("t1", "TimeoutError boom again", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out2 = repo.get_triage_inputs(user_id=u, run_id=r2["run_id"])
    assert out2["failures"][0]["is_novel"] is False


def test_retry_passed_and_family_label(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="rp",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "flaky", "retried": True}],
                           snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    f = out["failures"][0]
    assert f["retry_passed_in_run"] is True
    assert f["family_label"] == "unknown"  # default


def test_intermittent_same_sha(repo, org):
    u, o = org["user_id"], org["org_id"]
    # run A (commit sha1): el test pasa
    repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="a",
                       commit_sha="sha1", items=[],
                       results=[{"test_name": "t1", "status": "pass"}], snapshots=[])
    # run B (mismo sha1): el test falla
    rb = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="b",
                            commit_sha="sha1", items=[_item("t1", "TimeoutError x", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=rb["run_id"])
    assert out["failures"][0]["intermittent_same_sha"] is True


def test_has_green_baseline_and_dom_changed(repo, org):
    u, o = org["user_id"], org["org_id"]
    # run verde previo con baseline DOM
    repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="g",
                       commit_sha="sha2", items=[],
                       results=[{"test_name": "t1", "status": "pass"}],
                       snapshots=[{"test_name": "t1", "kind": "last_green",
                                   "content": "<html><button id='x'>Go</button></html>", "commit_sha": "sha2"}])
    # run con fallo y DOM distinto
    rf = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="f",
                            commit_sha="sha3", items=[_item("t1", "TimeoutError x", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}],
                            snapshots=[{"test_name": "t1", "kind": "failure",
                                        "content": "<html><button id='y'>Go</button></html>", "commit_sha": "sha3"}])
    out = repo.get_triage_inputs(user_id=u, run_id=rf["run_id"])
    f = out["failures"][0]
    assert f["has_green_baseline"] is True
    assert f["dom_changed"] is True


# ---------------------------------------------------------------------------
# Task 4: save_triage_verdicts / get_triage_for_run / set_family_label
# ---------------------------------------------------------------------------

def _verdict(failure_id, category="real", conf=0.85):
    return {"failure_id": failure_id, "category": category, "confidence": conf,
            "rule_applied": "R4_real_recurrent", "evidence_bundle": {"k": "v"},
            "requires_approval": False, "llm_assisted": False, "status": "resolved"}


def test_save_and_get_triage_verdicts_idempotent(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="v",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    fid = out["failures"][0]["failure_id"]
    n = repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[_verdict(fid)])
    assert n == 1
    # re-guardar (idempotente) → sigue habiendo 1, no 2
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[_verdict(fid, conf=0.9)])
    got = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])
    assert len(got) == 1
    assert got[0]["category"] == "real" and got[0]["confidence"] == 0.9
    assert got[0]["evidence_bundle"] == {"k": "v"}


def test_save_triage_verdicts_rejects_non_member(repo, org):
    with pytest.raises(PermissionError):
        repo.save_triage_verdicts(user_id=str(uuid.uuid4()), org_id=org["org_id"],
                                  run_id=str(uuid.uuid4()), verdicts=[])


def test_get_triage_for_run_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="g2",
                           items=[_item("t1", "x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    assert repo.get_triage_for_run(user_id=str(uuid.uuid4()), run_id=r["run_id"]) == []


def test_set_family_label(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="lbl",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    fam = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["family_id"]
    assert repo.set_family_label(user_id=u, family_id=fam, label="flaky") is True
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    assert out["failures"][0]["family_label"] == "flaky"


def test_set_family_label_rejects_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="nm-lbl",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    fam = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["family_id"]
    assert repo.set_family_label(user_id=str(uuid.uuid4()), family_id=fam, label="flaky") is False


def test_set_family_label_rejects_invalid(repo, org):
    with pytest.raises(ValueError):
        repo.set_family_label(user_id=org["user_id"], family_id=str(uuid.uuid4()), label="bogus")


def test_is_novel_two_failures_same_family_one_run(repo, org):
    u, o = org["user_id"], org["org_id"]
    # dos fallos con el MISMO error → misma familia (occurrence_count=2 en este run),
    # pero sin fallos en otros runs → ambos siguen siendo novel
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="nov2",
                           items=[_item("t1", "TimeoutError boom", 1.0),
                                  _item("t2", "TimeoutError boom", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"},
                                    {"test_name": "t2", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    assert all(f["is_novel"] is True for f in out["failures"])


def test_intermittent_not_cross_project(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.ingest_ci_run(user_id=u, org_id=o, project="projA", source="playwright", run_uid="ipa",
                       commit_sha="shX", items=[], results=[{"test_name": "t1", "status": "pass"}], snapshots=[])
    rb = repo.ingest_ci_run(user_id=u, org_id=o, project="projB", source="playwright", run_uid="ipb",
                            commit_sha="shX", items=[_item("t1", "TimeoutError x", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=rb["run_id"])
    assert out["failures"][0]["intermittent_same_sha"] is False  # distinto proyecto


def test_intermittent_false_when_only_fails(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="onlyfail",
                           commit_sha="sf", items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    assert out["failures"][0]["intermittent_same_sha"] is False


def test_dom_changed_false_when_identical(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="dgi",
                       commit_sha="s1", items=[], results=[{"test_name": "t1", "status": "pass"}],
                       snapshots=[{"test_name": "t1", "kind": "last_green", "content": "<html>same</html>", "commit_sha": "s1"}])
    rf = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="dgi2",
                            commit_sha="s2", items=[_item("t1", "TimeoutError x", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}],
                            snapshots=[{"test_name": "t1", "kind": "failure", "content": "<html>same</html>", "commit_sha": "s2"}])
    out = repo.get_triage_inputs(user_id=u, run_id=rf["run_id"])
    assert out["failures"][0]["has_green_baseline"] is True
    assert out["failures"][0]["dom_changed"] is False


# ---------------------------------------------------------------------------
# Task 2: update_triage_verdict
# ---------------------------------------------------------------------------

def test_update_triage_verdict_roundtrip(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="upd",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    fid = out["failures"][0]["failure_id"]
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[{
        "failure_id": fid, "category": "unknown", "confidence": 0.0,
        "rule_applied": "R6_unknown", "evidence_bundle": {"k": "v"},
        "requires_approval": True, "llm_assisted": False, "status": "needs_tiebreak"}])
    vid = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]["id"]
    ok = repo.update_triage_verdict(
        user_id=u, verdict_id=vid, category="real", confidence=0.70,
        requires_approval=True, llm_assisted=True, status="resolved",
        evidence_bundle={"k": "v", "tiebreak_reason": "porque sí"})
    assert ok is True
    got = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]
    assert got["category"] == "real" and got["confidence"] == 0.70
    assert got["llm_assisted"] is True and got["status"] == "resolved"
    assert got["evidence_bundle"]["tiebreak_reason"] == "porque sí"


def test_update_triage_verdict_rejects_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="updnm",
                           items=[_item("t1", "x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[{
        "failure_id": repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["failure_id"],
        "category": "unknown", "confidence": 0.0, "rule_applied": "R6_unknown",
        "evidence_bundle": None, "requires_approval": True, "llm_assisted": False,
        "status": "needs_tiebreak"}])
    vid = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]["id"]
    assert repo.update_triage_verdict(
        user_id=str(uuid.uuid4()), verdict_id=vid, category="real", confidence=0.70,
        requires_approval=True, llm_assisted=True, status="resolved",
        evidence_bundle={}) is False
