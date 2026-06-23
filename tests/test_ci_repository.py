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


def _failure_item(project, msg, seed):
    rec = FailureRecord(test_name="t", error_type="TimeoutError", message=msg,
                        trace=None, project=project, source="playwright")
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_ingest_run_persists_commit_sha(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="p", source="playwright",
                          items=[_failure_item("p", "TimeoutError x", 1.0)],
                          commit_sha="deadbeef")
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select commit_sha from public.test_runs where id = %s", (out["run_id"],))
            assert cur.fetchone()[0] == "deadbeef"


def test_record_test_results_stores_pass_and_fail(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="p", source="playwright",
                          items=[_failure_item("p", "TimeoutError x", 1.0)], commit_sha="sha")
    n = repo.record_test_results(user_id=u, org_id=o, run_id=out["run_id"], results=[
        {"test_name": "login", "status": "fail", "retried": False},
        {"test_name": "home", "status": "pass", "retried": False},
    ])
    assert n == 2
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_results where run_id = %s"
                        " and status = 'pass'", (out["run_id"],))
            assert cur.fetchone()[0] == 1
            cur.execute("select count(*) from public.test_results where run_id = %s"
                        " and status = 'fail'", (out["run_id"],))
            assert cur.fetchone()[0] == 1


def test_record_test_results_rejects_non_member(repo, org):
    out = repo.ingest_run(user_id=org["user_id"], org_id=org["org_id"], project="p",
                          source="playwright",
                          items=[_failure_item("p", "x", 0.3)], commit_sha="s")
    with pytest.raises(PermissionError):
        repo.record_test_results(user_id=str(uuid.uuid4()), org_id=org["org_id"],
                                 run_id=out["run_id"], results=[{"test_name": "t", "status": "pass"}])


def test_save_dom_snapshots_rejects_non_member(repo, org):
    with pytest.raises(PermissionError):
        repo.save_dom_snapshots(
            user_id=str(uuid.uuid4()), org_id=org["org_id"], project="p",
            snapshots=[{"test_name": "t", "kind": "failure", "content": "<html></html>"}],
        )


def test_save_dom_snapshots_stores_kind(repo, org):
    u, o = org["user_id"], org["org_id"]
    n = repo.save_dom_snapshots(user_id=u, org_id=o, project="p", snapshots=[
        {"test_name": "login", "kind": "failure", "content": "<html></html>", "commit_sha": "s"},
        {"test_name": "home", "kind": "last_green", "content": "<html>ok</html>"},
    ])
    assert n == 2
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.dom_snapshots where org_id = %s"
                        " and kind = 'last_green'", (o,))
            assert cur.fetchone()[0] == 1


def test_record_test_results_validates_keys(repo, org):
    out = repo.ingest_run(user_id=org["user_id"], org_id=org["org_id"], project="p",
                          source="playwright",
                          items=[_failure_item("p", "TimeoutError x", 1.0)], commit_sha="s")
    with pytest.raises(ValueError):
        repo.record_test_results(user_id=org["user_id"], org_id=org["org_id"],
                                 run_id=out["run_id"], results=[{"test_name": "t"}])


def test_save_dom_snapshots_validates_keys(repo, org):
    with pytest.raises(ValueError):
        repo.save_dom_snapshots(user_id=org["user_id"], org_id=org["org_id"], project="p",
                                snapshots=[{"test_name": "t"}])


def test_record_test_results_rejects_foreign_run(repo, org):
    # un run_id que no pertenece al org -> ValueError
    with pytest.raises(ValueError):
        repo.record_test_results(user_id=org["user_id"], org_id=org["org_id"],
                                 run_id=str(uuid.uuid4()),
                                 results=[{"test_name": "t", "status": "pass"}])


def test_record_test_results_rejects_bad_status(repo, org):
    out = repo.ingest_run(user_id=org["user_id"], org_id=org["org_id"], project="p",
                          source="playwright",
                          items=[_failure_item("p", "TimeoutError x", 1.0)], commit_sha="s")
    with pytest.raises(ValueError):
        repo.record_test_results(user_id=org["user_id"], org_id=org["org_id"],
                                 run_id=out["run_id"],
                                 results=[{"test_name": "t", "status": "exploded"}])


def test_save_dom_snapshots_rejects_bad_kind(repo, org):
    with pytest.raises(ValueError):
        repo.save_dom_snapshots(user_id=org["user_id"], org_id=org["org_id"], project="p",
                                snapshots=[{"test_name": "t", "kind": "bogus", "content": "<html></html>"}])


def test_ingest_ci_run_atomic_and_counts(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_ci_run(
        user_id=u, org_id=o, project="p", source="playwright",
        commit_sha="sha", run_uid="run-1",
        items=[_failure_item("p", "TimeoutError x", 1.0)],
        results=[{"test_name": "login", "status": "fail", "retried": False},
                 {"test_name": "home", "status": "pass", "retried": False}],
        snapshots=[{"test_name": "home", "kind": "last_green", "content": "<html>ok</html>",
                    "commit_sha": "sha"}],
    )
    assert out["deduplicated"] is False
    assert out["ingested"] == 1 and out["novel"] == 1
    assert out["results_recorded"] == 2 and out["snapshots_saved"] == 1
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_results where run_id = %s", (out["run_id"],))
            assert cur.fetchone()[0] == 2


def test_ingest_ci_run_idempotent_by_run_uid(repo, org):
    u, o = org["user_id"], org["org_id"]
    kw = dict(user_id=u, org_id=o, project="p", source="playwright", commit_sha="sha",
              run_uid="dup-1",
              items=[_failure_item("p", "TimeoutError x", 1.0)],
              results=[{"test_name": "t", "status": "fail"}],
              snapshots=[])
    first = repo.ingest_ci_run(**kw)
    second = repo.ingest_ci_run(**kw)
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert second["run_id"] == first["run_id"]
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_runs where org_id = %s and run_uid = %s",
                        (o, "dup-1"))
            assert cur.fetchone()[0] == 1


def test_ingest_ci_run_rolls_back_on_bad_snapshot(repo, org):
    u, o = org["user_id"], org["org_id"]
    with pytest.raises(ValueError):
        repo.ingest_ci_run(
            user_id=u, org_id=o, project="p", source="playwright", commit_sha="sha",
            run_uid="rollback-1",
            items=[_failure_item("p", "TimeoutError x", 1.0)],
            results=[{"test_name": "t", "status": "fail"}],
            snapshots=[{"test_name": "t", "kind": "bogus", "content": "<html></html>"}],
        )
    # Atomicidad: el run NO debe haberse creado.
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_runs where org_id = %s and run_uid = %s",
                        (o, "rollback-1"))
            assert cur.fetchone()[0] == 0


def test_ingest_ci_run_rejects_non_member(repo, org):
    with pytest.raises(PermissionError):
        repo.ingest_ci_run(user_id=str(uuid.uuid4()), org_id=org["org_id"], project="p",
                           source="playwright", run_uid="x", items=[], results=[], snapshots=[])
