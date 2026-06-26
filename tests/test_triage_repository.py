import os
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

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


def test_save_triage_verdicts_rejects_foreign_run(repo, org):
    """Un miembro del org A no puede guardar veredictos usando un run_id de org B."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    u_a, o_a = org["user_id"], org["org_id"]

    # Crear un segundo org con su propio usuario
    u_b = str(uuid.uuid4())
    email_b = f"test-{u_b[:8]}@test.internal"
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (u_b, email_b),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("test-org-b-" + u_b[:8], u_b),
            )
            o_b = str(cur.fetchone()[0])
        conn.commit()

    try:
        # Ingestar un run en org B
        r_b = repo.ingest_ci_run(user_id=u_b, org_id=o_b, project="p", source="playwright",
                                 run_uid="frn-b", items=[_item("t1", "x", 1.0)],
                                 results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
        # Usuario A (miembro de org A) intenta guardar veredictos sobre el run de org B → ValueError
        with pytest.raises(ValueError, match="run does not belong"):
            repo.save_triage_verdicts(user_id=u_a, org_id=o_a, run_id=r_b["run_id"], verdicts=[])
    finally:
        with psycopg.connect(DBURL) as conn:
            with conn.cursor() as cur:
                cur.execute("delete from public.organizations where id = %s", (o_b,))
                cur.execute("delete from auth.users where id = %s", (u_b,))
            conn.commit()


@pytest.fixture
def assurance_repo(repo):
    return repo


@pytest.fixture
def seeded_family(repo, org):
    """Extiende el fixture org con una familia, un failure y un veredicto para poblar
    engine_category. Devuelve {user_id, org_id, family_id}."""
    u, o = org["user_id"], org["org_id"]
    sig = f"sig-seed-{u[:8]}"
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            # Familia de defecto (scope='org')
            cur.execute(
                "insert into public.defect_families"
                " (scope, org_id, signature, title, occurrence_count)"
                " values ('org', %s, %s, 'Seeded Family', 1) returning id",
                (o, sig),
            )
            family_id = str(cur.fetchone()[0])
            # Run necesario para el failure
            cur.execute(
                "insert into public.test_runs (org_id, project, source)"
                " values (%s, 'p', 'playwright') returning id",
                (o,),
            )
            run_id = str(cur.fetchone()[0])
            # Failure enlazado a la familia
            cur.execute(
                "insert into public.failures"
                " (run_id, org_id, test_name, message, fingerprint, defect_family_id)"
                " values (%s, %s, 'seed_test', 'err', 'fp-seed', %s) returning id",
                (run_id, o, family_id),
            )
            failure_id = str(cur.fetchone()[0])
            # Veredicto con category='real' → engine_category quedará 'real'
            cur.execute(
                "insert into public.triage_verdicts"
                " (failure_id, run_id, org_id, category, confidence, rule_applied)"
                " values (%s, %s, %s, 'real', 0.9, 'R4_real_recurrent')",
                (failure_id, run_id, o),
            )
        conn.commit()
    yield {"user_id": u, "org_id": o, "family_id": family_id}
    # Cleanup: la familia (y su cascada) se elimina cuando se borra el org en el fixture org


def test_get_triage_inputs_wrong_org_isolation(repo, org):
    """Un miembro del org B no puede ver los inputs de triaje de un run del org A."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    u_a, o_a = org["user_id"], org["org_id"]

    # Crear segundo org B
    u_b = str(uuid.uuid4())
    email_b = f"test-{u_b[:8]}@test.internal"
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (u_b, email_b),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("test-org-b2-" + u_b[:8], u_b),
            )
            o_b = str(cur.fetchone()[0])
        conn.commit()

    try:
        # Run pertenece a org A
        r_a = repo.ingest_ci_run(user_id=u_a, org_id=o_a, project="p", source="playwright",
                                 run_uid="iso-a", items=[_item("t1", "x", 1.0)],
                                 results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
        # Usuario B (miembro de org B) consulta el run de org A → run: None
        out = repo.get_triage_inputs(user_id=u_b, run_id=r_a["run_id"])
        assert out["run"] is None
    finally:
        with psycopg.connect(DBURL) as conn:
            with conn.cursor() as cur:
                cur.execute("delete from public.organizations where id = %s", (o_b,))
                cur.execute("delete from auth.users where id = %s", (u_b,))
            conn.commit()


# ---------------------------------------------------------------------------
# Task 2 (F5a): triage_corrections + get_calibration_metrics
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_set_family_label_records_correction(assurance_repo, seeded_family):
    # seeded_family: dict with user_id, org_id, family_id, and a recent verdict category 'real'
    repo, ctx = assurance_repo, seeded_family
    ok = repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"],
                               label="flaky", reason="histórico flaky")
    assert ok is True
    metrics = repo.get_calibration_metrics(user_id=ctx["user_id"], org_id=ctx["org_id"])
    assert metrics["total"] == 1
    # engine dijo 'real', humano dijo 'flaky' → no es acierto
    assert metrics["aciertos"] == 0
    assert metrics["familias_calibradas"] == 1
    assert metrics["por_categoria"].get("flaky") == 1


@pytest.mark.integration
def test_set_family_label_non_member_returns_false(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    assert repo.set_family_label(user_id=str(uuid.uuid4()), family_id=ctx["family_id"],
                                 label="flaky") is False


@pytest.mark.integration
def test_get_calibration_metrics_non_member_is_none(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    assert repo.get_calibration_metrics(user_id=str(uuid.uuid4()), org_id=ctx["org_id"]) is None


@pytest.mark.integration
def test_set_family_label_invalid_label_raises(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    with pytest.raises(ValueError):
        repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"], label="bogus")


# ---------------------------------------------------------------------------
# Task 3 (A3 + A4): métrica del foso honesta + firma exacta sin centroide
# ---------------------------------------------------------------------------


def _set_recent_verdict(ctx: dict, *, category: str, llm_assisted: bool) -> None:
    # rule_applied es irrelevante aquí; solo category/llm_assisted determinan engine_category
    """Inserta (o reemplaza el último) un triage_verdict para la familia del fixture.

    El fixture seeded_family ya sembró un failure y un veredicto; aquí insertamos
    uno nuevo más reciente para controlar category/llm_assisted en el test.
    """
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            # Obtener un failure_id vinculado a la familia
            cur.execute(
                "select id, run_id from public.failures where defect_family_id = %s limit 1",
                (ctx["family_id"],),
            )
            row = cur.fetchone()
            assert row is not None, "seeded_family debe tener al menos un failure"
            failure_id, run_id = row[0], row[1]
            cur.execute(
                "insert into public.triage_verdicts"
                " (failure_id, run_id, org_id, category, confidence, rule_applied,"
                "  requires_approval, llm_assisted, evidence_bundle, status)"
                " values (%s, %s, %s, %s, 0.8, 'R4_real_recurrent', false, %s, '{}', 'resolved')",
                (failure_id, run_id, ctx["org_id"], category, llm_assisted),
            )
        conn.commit()


def _last_correction(family_id: str) -> dict:
    """Devuelve la corrección más reciente de triage_corrections para la familia."""
    with psycopg.connect(DBURL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select * from public.triage_corrections"
                " where family_id = %s order by corrected_at desc limit 1",
                (family_id,),
            )
            row = cur.fetchone()
            assert row is not None, "debe existir al menos una corrección"
            return dict(row)


@pytest.mark.integration
def test_engine_category_is_unknown_when_llm_assisted(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    _set_recent_verdict(ctx, category="flaky", llm_assisted=True)
    repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"],
                          label="real", reason="r")
    row = _last_correction(ctx["family_id"])
    assert row["engine_category"] == "unknown"   # motor fue ambiguo; LLM decidió
    assert row["human_category"] == "real"
    assert row["reason"] == "r"
    assert row["source"] == "family_label"
    assert str(row["corrected_by"]) == ctx["user_id"]


@pytest.mark.integration
def test_engine_category_is_verdict_when_not_llm(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    _set_recent_verdict(ctx, category="real", llm_assisted=False)
    repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"], label="real")
    assert _last_correction(ctx["family_id"])["engine_category"] == "real"


@pytest.mark.integration
def test_query_candidates_returns_null_centroid_family(assurance_repo, org):
    """Una familia con firma exacta pero centroid NULL debe ser devuelta por
    _query_candidates para evitar duplicados que romperían uq_defect_families_org_signature."""
    from pgvector.psycopg import register_vector
    repo = assurance_repo
    u, o = org["user_id"], org["org_id"]
    sig = f"null-centroid-{uuid.uuid4().hex[:8]}"

    # Insertar familia con centroid NULL
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into public.defect_families"
                " (scope, org_id, signature, title, occurrence_count, centroid)"
                " values ('org', %s, %s, 'No centroid yet', 1, NULL) returning id",
                (o, sig),
            )
            fam_id = str(cur.fetchone()[0])
        conn.commit()

    # Llamar _query_candidates con la firma exacta → debe devolver la familia
    with psycopg.connect(DBURL, row_factory=dict_row) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            candidates = repo._query_candidates(
                cur, org_id=o, fingerprint=sig, embedding=[0.0] * 384
            )

    ids = [c.family_id for c in candidates]
    assert fam_id in ids, (
        f"familia {fam_id} con centroid NULL no fue devuelta por _query_candidates: {ids}"
    )
