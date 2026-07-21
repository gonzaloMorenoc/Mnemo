from unittest.mock import MagicMock

from src.knowledge.proposal_service import KnowledgeProposalService

_RCA = {"root_cause": "c", "why_it_happened": "w", "how_to_fix": "h",
        "suggested_fix_steps": ["s"], "citations": [], "confidence": 0.7}
_UNSET = object()


def _svc(*, candidates, upsert=_UNSET, remaining=0, family_ctx=None, rca=_RCA):
    repo = MagicMock()
    repo.candidate_families.return_value = candidates
    repo.upsert_proposal.return_value = {"id": "p"} if upsert is _UNSET else upsert
    repo.count_candidate_families.return_value = remaining
    assurance = MagicMock()
    assurance.get_family_with_failures.return_value = (
        family_ctx if family_ctx is not None
        else {"family": {"id": "f1", "title": "T1"}, "failures": [{"project": "web"}]})
    analyzer = MagicMock()
    analyzer.analyze_structured.return_value = rca
    svc = KnowledgeProposalService(repo=repo, assurance_repo=assurance, analyzer=analyzer)
    return svc, repo, assurance, analyzer


def test_generate_creates_proposals_for_each_candidate():
    svc, repo, assurance, analyzer = _svc(candidates=[
        {"id": "f1", "title": "T1", "occurrence_count": 3, "run_id": "r1"},
        {"id": "f2", "title": "T2", "occurrence_count": 1, "run_id": None},
    ])
    out = svc.generate(user_id="u", org_id="o")
    assert out == {"created": 2, "failed": 0, "remaining": 0}
    assert repo.upsert_proposal.call_count == 2
    kw = repo.upsert_proposal.call_args_list[0].kwargs
    assert kw["kind"] == "leccion" and kw["defect_family_id"] == "f1" and kw["run_id"] == "r1"
    assert kw["created_by"] == "u" and kw["org_id"] == "o"
    assert "c" in kw["challenge"] and "h" in kw["approach"]   # mapeo aplicado
    analyzer.analyze_structured.assert_called()


def test_generate_passes_cap_and_family_ids_to_repo():
    svc, repo, _, _ = _svc(candidates=[], remaining=7)
    out = svc.generate(user_id="u", org_id="o", cap=3, family_ids=["f9"])
    repo.candidate_families.assert_called_once_with(
        user_id="u", org_id="o", limit=3, family_ids=["f9"])
    assert out == {"created": 0, "failed": 0, "remaining": 7}


def test_generate_one_failure_does_not_abort_batch():
    svc, repo, assurance, analyzer = _svc(candidates=[
        {"id": "f1", "title": "T1", "run_id": None},
        {"id": "f2", "title": "T2", "run_id": None},
    ])
    analyzer.analyze_structured.side_effect = [RuntimeError("llm down"), _RCA]
    out = svc.generate(user_id="u", org_id="o")
    assert out["created"] == 1 and out["failed"] == 1


def test_generate_upsert_noop_counts_as_failed():
    svc, repo, _, _ = _svc(candidates=[{"id": "f1", "title": "T", "run_id": None}], upsert=None)
    out = svc.generate(user_id="u", org_id="o")
    assert out == {"created": 0, "failed": 1, "remaining": 0}


def test_approve_delegates_to_repo():
    svc, repo, _, _ = _svc(candidates=[])
    repo.approve.return_value = {"id": "k1", "kind": "leccion"}
    out = svc.approve(user_id="u", proposal_id="p", kind="leccion", title="T",
                      challenge="c", approach="a", domain="d", outcome="o", tags=["x"])
    assert out == {"id": "k1", "kind": "leccion"}
    assert repo.approve.call_args.kwargs["proposal_id"] == "p"


def test_reject_delegates_to_repo():
    svc, repo, _, _ = _svc(candidates=[])
    repo.reject.return_value = True
    assert svc.reject(user_id="u", proposal_id="p", reason="dup") is True


def test_list_delegates_to_repo():
    svc, repo, _, _ = _svc(candidates=[])
    repo.list_proposals.return_value = [{"id": "p"}]
    assert svc.list(user_id="u", org_id="o") == [{"id": "p"}]
