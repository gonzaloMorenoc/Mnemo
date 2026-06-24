from src.actions.base import ActionProposal, NullCodeHost


def test_action_proposal_holds_fields():
    p = ActionProposal(kind="ticket", payload={"title": "x"}, summary="s")
    assert p.kind == "ticket" and p.payload["title"] == "x" and p.summary == "s"


def test_null_codehost_returns_stub_refs_and_writes_nothing():
    ch = NullCodeHost()
    assert ch.create_issue(title="t", body="b", labels=["x"]).startswith("stub://")
    assert ch.open_draft_pr(title="t", body="b", patch="p").startswith("stub://")
