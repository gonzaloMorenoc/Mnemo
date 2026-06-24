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
    repo.get_action.return_value = {"id": "a1", "org_id": "o", "kind": "ticket", "status": "proposed",
                                    "payload": {"title": "T", "body": "B", "labels": ["bug"]}}
    repo.approve_action.return_value = True
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "https://github.com/o/r/issues/9"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "materialized": True,
                   "artifact_ref": "https://github.com/o/r/issues/9"}
    assert codehost.create_issue.call_args.kwargs["marker"] == "mnemo:action:a1"
    assert repo.materialize_action.call_args.kwargs["artifact_ref"] == "https://github.com/o/r/issues/9"


def test_approve_quarantine_materializes_debt_ticket():
    repo = MagicMock()
    repo.get_action.return_value = {
        "id": "a2", "org_id": "o", "kind": "quarantine", "status": "proposed",
        "payload": {"debt_ticket": {"title": "[Flaky] t", "body": "B", "labels": ["flaky"]},
                    "annotation": {"test_name": "t"}}}
    repo.approve_action.return_value = True
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "https://github.com/o/r/issues/22"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a2")
    assert out["materialized"] is True and out["artifact_ref"] == "https://github.com/o/r/issues/22"
    kw = codehost.create_issue.call_args.kwargs
    assert kw["title"] == "[Flaky] t" and kw["body"] == "B"


def test_approve_rejected_or_missing_returns_false():
    repo = MagicMock()
    repo.get_action.return_value = None
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    assert svc.approve_action(user_id="u", action_id="x") == {
        "approved": False, "materialized": False, "artifact_ref": None}
    codehost.create_issue.assert_not_called()
    repo.approve_action.assert_not_called()


def test_approve_already_materialized_is_idempotent():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "org_id": "o", "kind": "ticket",
                                    "status": "materialized",
                                    "artifact_ref": "https://github.com/o/r/issues/1", "payload": {}}
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "materialized": True,
                   "artifact_ref": "https://github.com/o/r/issues/1"}
    codehost.create_issue.assert_not_called()
    repo.approve_action.assert_not_called()


def test_approve_retries_materialize_when_already_approved():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "org_id": "o", "kind": "ticket", "status": "approved",
                                    "artifact_ref": None,
                                    "payload": {"title": "T", "body": "B", "labels": []}}
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "https://github.com/o/r/issues/7"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out["materialized"] is True and out["artifact_ref"] == "https://github.com/o/r/issues/7"
    repo.approve_action.assert_not_called()         # ya estaba approved
    codehost.create_issue.assert_called_once()


def test_approve_self_heal_stays_approved_without_materializing():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a3", "org_id": "o", "kind": "self_heal",
                                    "status": "proposed", "payload": {"suggested_locator": "x"}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a3")
    assert out == {"approved": True, "materialized": False, "artifact_ref": None}
    codehost.create_issue.assert_not_called()
    repo.materialize_action.assert_not_called()


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
