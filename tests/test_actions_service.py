from unittest.mock import MagicMock

from src.actions.base import ActionProposal
from src.actions.service import ActionService


def _svc(verdicts):
    repo = MagicMock()
    repo.get_run_actionable_verdicts.return_value = verdicts
    repo.get_family_with_failures.return_value = {"family": {"title": "F"}, "failures": [{"x": 1}]}
    repo.save_actions.return_value = len(verdicts)
    quarantine = MagicMock()
    quarantine.propose.return_value = ActionProposal("quarantine", {"debt_ticket": {"title": "t"}}, "q")
    ticket = MagicMock()
    ticket.propose.return_value = ActionProposal("ticket", {"title": "t"}, "tk")
    svc = ActionService(repo=repo, actuators={"flaky": quarantine, "real": ticket})
    return svc, repo, quarantine, ticket


def test_propose_maps_categories_and_skips_unmapped():
    verdicts = [
        {"verdict_id": "v1", "category": "flaky", "org_id": "o", "evidence_bundle": {}, "test_name": "a"},
        {"verdict_id": "v2", "category": "real", "org_id": "o", "evidence_bundle": {}, "test_name": "b",
         "defect_family_id": "fam"},
        {"verdict_id": "v3", "category": "maintenance", "org_id": "o", "evidence_bundle": {}, "test_name": "c"},
    ]
    svc, repo, quarantine, ticket = _svc(verdicts)
    counts = svc.propose_actions(user_id="u", run_id="r")
    assert counts == {"quarantine": 1, "ticket": 1, "skipped": 1}
    # el ticket recibió context con family+failures (fetch de get_family_with_failures)
    _, ctx = ticket.propose.call_args.args
    assert ctx["family"]["title"] == "F" and ctx["test_name"] == "b"
    # quarantine recibió test_name pero NO se le buscó familia
    repo.get_family_with_failures.assert_called_once()   # solo para el 'real'
    repo.save_actions.assert_called_once()
    saved = repo.save_actions.call_args.kwargs["actions"]
    assert {a["kind"] for a in saved} == {"quarantine", "ticket"}


def test_propose_no_actionable_does_not_save():
    svc, repo, _, _ = _svc([])
    assert svc.propose_actions(user_id="u", run_id="r") == {"quarantine": 0, "ticket": 0, "skipped": 0}
    repo.save_actions.assert_not_called()


def test_approve_materializes_via_codehost_and_records_ref():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "kind": "ticket",
                                    "payload": {"title": "T", "body": "B", "labels": ["bug"]}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "stub://issue/9"
    svc = ActionService(repo=repo, actuators={}, codehost=codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "artifact_ref": "stub://issue/9"}
    codehost.create_issue.assert_called_once()
    assert repo.approve_action.call_args.kwargs["artifact_ref"] == "stub://issue/9"


def test_reject_delegates_to_repo():
    repo = MagicMock()
    repo.reject_action.return_value = True
    svc = ActionService(repo=repo, actuators={})
    assert svc.reject_action(user_id="u", action_id="a1", reason="dup") is True
