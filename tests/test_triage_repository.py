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
