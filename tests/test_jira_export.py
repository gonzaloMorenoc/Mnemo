import pytest

from src.jira.export import parse_jira_export

SEARCH_JSON = b"""{
  "issues": [
    {"key": "PROJ-1", "fields": {"summary": "Login timeout",
      "description": {"type": "doc", "content": [{"type": "paragraph",
        "content": [{"type": "text", "text": "waited 30000ms"}]}]},
      "issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
    {"key": "PROJ-2", "fields": {"summary": "A story",
      "description": "ignore me", "issuetype": {"name": "Story"},
      "status": {"name": "Done"}}}
  ]
}"""

CSV_EXPORT = (
    b"Issue key,Summary,Description,Issue Type,Status\r\n"
    b"PROJ-9,Checkout fails,NullPointer in pay,Bug,Open\r\n"
    b"PROJ-10,Nice to have,whatever,Story,Backlog\r\n"
)


def test_parse_export_json_only_bugs():
    bugs = parse_jira_export(SEARCH_JSON)
    assert len(bugs) == 1
    assert bugs[0].key == "PROJ-1"
    assert "30000ms" in bugs[0].description
    assert bugs[0].issue_type == "Bug"


def test_parse_export_csv_only_bugs():
    bugs = parse_jira_export(CSV_EXPORT)
    assert len(bugs) == 1
    assert bugs[0].key == "PROJ-9"
    assert bugs[0].summary == "Checkout fails"
    assert bugs[0].status == "Open"


def test_parse_export_invalid_raises():
    with pytest.raises(ValueError):
        parse_jira_export(b"definitely not jira")
