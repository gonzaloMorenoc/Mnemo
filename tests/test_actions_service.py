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
    assert counts == {"quarantine": 1, "ticket": 1, "self_heal": 0, "skipped": 1}
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
    assert svc.propose_actions(user_id="u", run_id="r") == {"quarantine": 0, "ticket": 0, "self_heal": 0, "skipped": 0}
    repo.save_actions.assert_not_called()


def test_approve_materializes_via_codehost_and_records_ref():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "kind": "ticket", "status": "proposed",
                                    "payload": {"title": "T", "body": "B", "labels": ["bug"]}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "stub://issue/9"
    svc = ActionService(repo=repo, actuators={}, codehost=codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "artifact_ref": "stub://issue/9"}
    codehost.create_issue.assert_called_once()
    assert repo.approve_action.call_args.kwargs["artifact_ref"] == "stub://issue/9"


def test_approve_quarantine_materializes_debt_ticket():
    repo = MagicMock()
    repo.get_action.return_value = {
        "id": "a2", "kind": "quarantine", "status": "proposed",
        "payload": {"debt_ticket": {"title": "[Flaky] t", "body": "B", "labels": ["flaky"]},
                    "annotation": {"test_name": "t"}}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "stub://issue/22"
    svc = ActionService(repo=repo, actuators={}, codehost=codehost)
    out = svc.approve_action(user_id="u", action_id="a2")
    assert out == {"approved": True, "artifact_ref": "stub://issue/22"}
    # materializó el ticket de deuda (no el annotation)
    kw = codehost.create_issue.call_args.kwargs
    assert kw["title"] == "[Flaky] t" and kw["body"] == "B"
    assert repo.approve_action.call_args.kwargs["artifact_ref"] == "stub://issue/22"


def test_approve_non_proposed_does_not_materialize():
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "kind": "ticket", "status": "approved",
                                    "payload": {"title": "T"}}
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost=codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": False, "artifact_ref": None}
    codehost.create_issue.assert_not_called()        # invariante Nivel-2
    repo.approve_action.assert_not_called()


def test_propose_none_proposal_counts_skipped():
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_run_actionable_verdicts.return_value = [
        {"verdict_id": "v1", "category": "flaky", "org_id": "o", "evidence_bundle": {}, "test_name": "a"}]
    actuator = MagicMock()
    actuator.propose.return_value = None             # actuador que no propone
    svc = ActionService(repo=repo, actuators={"flaky": actuator})
    assert svc.propose_actions(user_id="u", run_id="r") == {"quarantine": 0, "ticket": 0, "self_heal": 0, "skipped": 1}
    repo.save_actions.assert_not_called()


def test_reject_delegates_to_repo():
    repo = MagicMock()
    repo.reject_action.return_value = True
    svc = ActionService(repo=repo, actuators={})
    assert svc.reject_action(user_id="u", action_id="a1", reason="dup") is True


def test_maintenance_uses_selfheal_context():
    from unittest.mock import MagicMock
    from src.actions.base import ActionProposal
    repo = MagicMock()
    repo.get_run_actionable_verdicts.return_value = [
        {"verdict_id": "v1", "category": "maintenance", "org_id": "o", "evidence_bundle": {},
         "test_name": "t", "failure_id": "f1"}]
    repo.get_selfheal_context.return_value = {"error_message": "e", "trace": None,
                                              "green_dom": "<a/>", "failure_dom": "<a/>"}
    repo.save_actions.return_value = 1
    sh = MagicMock()
    sh.propose.return_value = ActionProposal("self_heal", {"suggested_locator": "x"}, "s")
    svc = ActionService(repo=repo, actuators={"maintenance": sh})
    counts = svc.propose_actions(user_id="u", run_id="r")
    repo.get_selfheal_context.assert_called_once_with(user_id="u", failure_id="f1")
    _, ctx = sh.propose.call_args.args
    assert ctx["green_dom"] == "<a/>" and ctx["error_message"] == "e"
    assert counts.get("self_heal", 0) == 1 or counts == {"quarantine": 0, "ticket": 0, "self_heal": 1, "skipped": 0}
