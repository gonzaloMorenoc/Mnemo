from unittest.mock import MagicMock

from src.triage.service import TriageService


def _failure(test_name, error_type, message, **over):
    base = {
        "failure_id": f"fid-{test_name}", "fingerprint": f"fp-{test_name}",
        "family_id": f"fam-{test_name}", "lineage_projects": ["p"],
        "error_type": error_type, "message": message, "trace": None,
        "is_novel": True, "family_label": "unknown", "retry_passed_in_run": False,
        "intermittent_same_sha": False, "has_green_baseline": False, "dom_changed": False,
    }
    base.update(over)
    return base


def _svc(failures, threshold=3):
    repo = MagicMock()
    repo.get_triage_inputs.return_value = {
        "run": {"id": "r1", "org_id": "o1", "project": "p", "commit_sha": "sha"},
        "failures": failures,
    }
    repo.save_triage_verdicts.return_value = len(failures)
    return TriageService(repo=repo, threshold=threshold), repo


def test_non_member_returns_empty_and_does_not_save():
    repo = MagicMock()
    repo.get_triage_inputs.return_value = {"run": None, "failures": []}
    svc = TriageService(repo=repo, threshold=3)
    assert svc.triage_run(user_id="u", run_id="r1") == {}
    repo.save_triage_verdicts.assert_not_called()


def test_flaky_classified_and_persisted():
    svc, repo = _svc([_failure("t1", "Error", "boom", known_flaky_family=False,
                               retry_passed_in_run=True)])
    counts = svc.triage_run(user_id="u", run_id="r1")
    assert counts["flaky"] == 1
    _, kw = repo.save_triage_verdicts.call_args
    v = kw["verdicts"][0]
    assert v["failure_id"] == "fid-t1" and v["category"] == "flaky"
    assert v["status"] == "resolved" and v["evidence_bundle"]["rule_applied"] == "R1_flaky"


def test_mass_cofailure_makes_infra():
    # 3 fallos con firma de infra → mass_cofailure True → categoría infra (R2)
    fs = [_failure(f"t{i}", "Error", "connect ECONNREFUSED 127.0.0.1") for i in range(3)]
    svc, repo = _svc(fs, threshold=3)
    counts = svc.triage_run(user_id="u", run_id="r1")
    assert counts["infra"] == 3
    # con umbral 4, los mismos 3 NO son co-fallo masivo → no infra
    svc2, _ = _svc([_failure(f"t{i}", "Error", "connect ECONNREFUSED x") for i in range(3)], threshold=4)
    assert svc2.triage_run(user_id="u", run_id="r1").get("infra", 0) == 0


def test_ambiguous_marked_needs_tiebreak():
    # locator error sin baseline/dom_changed → ambiguo
    svc, repo = _svc([_failure("t1", "TimeoutError", "waiting for locator")])
    svc.triage_run(user_id="u", run_id="r1")
    v = repo.save_triage_verdicts.call_args.kwargs["verdicts"][0]
    assert v["category"] == "unknown" and v["status"] == "needs_tiebreak"
    assert v["requires_approval"] is True and v["llm_assisted"] is False


def test_real_recurrent_verdict_fields_persisted():
    # aserción + recurrente (no novel) → real @ 0.85, sin aprobación
    svc, repo = _svc([_failure("t1", "AssertionError", "expect(x).toBe(y)", is_novel=False)])
    svc.triage_run(user_id="u", run_id="r1")
    v = repo.save_triage_verdicts.call_args.kwargs["verdicts"][0]
    assert v["category"] == "real" and v["confidence"] == 0.85
    assert v["rule_applied"] == "R4_real_recurrent" and v["requires_approval"] is False
    assert v["llm_assisted"] is False and v["status"] == "resolved"


def test_resolve_tiebreaks_resolves_only_pending():
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [
        {"id": "v1", "failure_id": "f1", "category": "real", "confidence": 0.85,
         "rule_applied": "R4_real_recurrent", "evidence_bundle": {}, "requires_approval": False,
         "llm_assisted": False, "status": "resolved"},
        {"id": "v2", "failure_id": "f2", "category": "unknown", "confidence": 0.0,
         "rule_applied": "R6_unknown", "evidence_bundle": {"signals": []}, "requires_approval": True,
         "llm_assisted": False, "status": "needs_tiebreak"},
    ]
    tb = MagicMock()
    tb.resolve.return_value = ("flaky", "intermitente")
    svc = TriageService(repo=repo, tiebreaker=tb)
    out = svc.resolve_tiebreaks(user_id="u", run_id="r1")
    assert out == {"resolved": 1, "pending": 0}
    repo.update_triage_verdict.assert_called_once()
    kw = repo.update_triage_verdict.call_args.kwargs
    assert kw["verdict_id"] == "v2" and kw["category"] == "flaky" and kw["confidence"] == 0.70
    assert kw["llm_assisted"] is True and kw["requires_approval"] is True and kw["status"] == "resolved"
    assert kw["evidence_bundle"]["tiebreak_reason"] == "intermitente"
    assert kw["evidence_bundle"]["tiebreak_category"] == "flaky"
    assert kw["evidence_bundle"]["llm_assisted"] is True


def test_resolve_tiebreaks_leaves_pending_when_undecided():
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [
        {"id": "v2", "failure_id": "f2", "category": "unknown", "confidence": 0.0,
         "rule_applied": "R6_unknown", "evidence_bundle": {}, "requires_approval": True,
         "llm_assisted": False, "status": "needs_tiebreak"},
    ]
    tb = MagicMock()
    tb.resolve.return_value = None
    svc = TriageService(repo=repo, tiebreaker=tb)
    assert svc.resolve_tiebreaks(user_id="u", run_id="r1") == {"resolved": 0, "pending": 1}
    repo.update_triage_verdict.assert_not_called()


def test_resolve_tiebreaks_no_pending():
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [{"id": "v1", "status": "resolved", "evidence_bundle": {}}]
    svc = TriageService(repo=repo, tiebreaker=MagicMock())
    assert svc.resolve_tiebreaks(user_id="u", run_id="r1") == {"resolved": 0, "pending": 0}
