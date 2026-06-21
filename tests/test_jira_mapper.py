from src.jira.mapper import bug_to_record
from src.jira.models import JiraBug


def test_bug_to_record_maps_fields():
    bug = JiraBug(key="PROJ-1", summary="Login timeout", description="waited 30s",
                  issue_type="Bug", status="Open", url="https://x/browse/PROJ-1")
    rec = bug_to_record(bug, project="cliente-a")
    assert rec.test_name == "PROJ-1"
    assert rec.error_type == "Bug"
    assert rec.message == "Login timeout"
    assert rec.trace == "waited 30s"
    assert rec.project == "cliente-a"
    assert rec.source == "jira"


def test_bug_to_record_empty_description_is_none():
    bug = JiraBug(key="P-2", summary="s", description="", issue_type="Bug", status="Open")
    rec = bug_to_record(bug, project="p")
    assert rec.trace is None
