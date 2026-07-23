"""Cliente Jira: timeout explícito (default 75 s de la librería > 55 s del proxy)
y resolución en fetch_issue (el import la necesita para el outcome)."""
from unittest.mock import patch

from src.jira.client import JiraApiClient


def test_constructor_pasa_timeout():
    with patch("src.jira.client.Jira") as mock_jira:
        JiraApiClient("https://a.atlassian.net", "e@x.com", "tok", timeout=10)
    assert mock_jira.call_args.kwargs["timeout"] == 10


def test_constructor_timeout_por_defecto_10():
    with patch("src.jira.client.Jira") as mock_jira:
        JiraApiClient("https://a.atlassian.net", "e@x.com", "tok")
    assert mock_jira.call_args.kwargs["timeout"] == 10


def test_fetch_issue_trae_resolucion():
    with patch("src.jira.client.Jira") as mock_jira:
        api = mock_jira.return_value
        api.issue.return_value = {
            "key": "PAY-1",
            "fields": {"summary": "S", "description": "D",
                       "resolution": {"name": "Fixed"},
                       "resolutiondate": "2026-07-01T10:00:00.000+0000"}}
        client = JiraApiClient("https://a.atlassian.net", "e@x.com", "tok")
        issue = client.fetch_issue("PAY-1")
    assert issue.resolution == "Fixed"
    assert issue.resolution_date.startswith("2026-07-01")
    assert "resolution" in api.issue.call_args.kwargs["fields"]


def test_fetch_issue_sin_resolucion():
    with patch("src.jira.client.Jira") as mock_jira:
        api = mock_jira.return_value
        api.issue.return_value = {"key": "PAY-2",
                                  "fields": {"summary": "S", "description": None,
                                             "resolution": None}}
        client = JiraApiClient("https://a.atlassian.net", "e@x.com", "tok")
        issue = client.fetch_issue("PAY-2")
    assert issue.resolution == ""
    assert issue.resolution_date == ""
