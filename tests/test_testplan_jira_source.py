"""Tests for src/testplan/jira_source.py (TDD – written before implementation)."""
import pytest

from src.testplan.jira_source import hu_text_from_jira, parse_issue_key
from src.jira.client import JiraApiClient


# ---------------------------------------------------------------------------
# parse_issue_key
# ---------------------------------------------------------------------------

class TestParseIssueKey:
    def test_browse_url(self):
        url = "https://acme.atlassian.net/browse/DIA-1234"
        assert parse_issue_key(url) == "DIA-1234"

    def test_selected_issue_param(self):
        url = "https://acme.atlassian.net/project/abc?selectedIssue=PRJ-99"
        assert parse_issue_key(url) == "PRJ-99"

    def test_bad_url_raises(self):
        with pytest.raises(ValueError, match="key"):
            parse_issue_key("https://acme.atlassian.net/projects/DIA")

    def test_multi_segment_project_key(self):
        url = "https://foo.atlassian.net/browse/MYAPP-456"
        assert parse_issue_key(url) == "MYAPP-456"


# ---------------------------------------------------------------------------
# JiraApiClient.fetch_issue
# ---------------------------------------------------------------------------

class _FakeJiraForIssue:
    """Imita atlassian.Jira para una llamada a issue()."""

    def __init__(self, payload: dict):
        self.url = "https://acme.atlassian.net"
        self._payload = payload

    def issue(self, key: str, fields: str):
        return self._payload


def _client_with(fake):
    c = JiraApiClient.__new__(JiraApiClient)
    c._jira = fake
    return c


class TestFetchIssue:
    def test_returns_jira_issue(self):
        payload = {
            "key": "DIA-1234",
            "fields": {
                "summary": "Login fails on mobile",
                "description": "Users cannot log in from iOS devices.",
            },
        }
        c = _client_with(_FakeJiraForIssue(payload))
        issue = c.fetch_issue("DIA-1234")
        assert issue.key == "DIA-1234"
        assert issue.summary == "Login fails on mobile"
        assert "iOS" in issue.description

    def test_adf_description_extracted(self):
        payload = {
            "key": "DIA-5",
            "fields": {
                "summary": "ADF test",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Hello ADF world"}],
                        }
                    ],
                },
            },
        }
        c = _client_with(_FakeJiraForIssue(payload))
        issue = c.fetch_issue("DIA-5")
        assert issue.description == "Hello ADF world"

    def test_wraps_errors(self):
        from src.jira.client import JiraApiError

        class _Boom:
            url = "https://acme.atlassian.net"

            def issue(self, key, fields):
                raise RuntimeError("403 Forbidden")

        c = _client_with(_Boom())
        with pytest.raises(JiraApiError):
            c.fetch_issue("DIA-1")

    def test_missing_description_empty_string(self):
        payload = {
            "key": "DIA-2",
            "fields": {"summary": "No desc", "description": None},
        }
        c = _client_with(_FakeJiraForIssue(payload))
        issue = c.fetch_issue("DIA-2")
        assert issue.description == ""


# ---------------------------------------------------------------------------
# hu_text_from_jira
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock


class TestHuTextFromJira:
    def _make_repo(self, creds):
        repo = MagicMock()
        repo.get_jira_credentials.return_value = creds
        return repo

    def _make_fake_jira(self, summary, description):
        payload = {
            "key": "DIA-1234",
            "fields": {
                "summary": summary,
                "description": description,
            },
        }
        return _FakeJiraForIssue(payload)

    def test_composes_summary_and_description(self, monkeypatch):
        repo = self._make_repo(
            {"base_url": "https://acme.atlassian.net", "email": "a@b.com", "token": "tok"}
        )
        fake_jira = self._make_fake_jira(
            "Login fails on mobile",
            "Users cannot log in from iOS devices.",
        )

        def _fake_client(base_url, email, token):
            c = JiraApiClient.__new__(JiraApiClient)
            c._jira = fake_jira
            return c

        monkeypatch.setattr("src.testplan.jira_source.JiraApiClient", _fake_client)

        text = hu_text_from_jira(
            url="https://acme.atlassian.net/browse/DIA-1234",
            org_id="org-1",
            user_id="user-1",
            repo=repo,
        )
        assert "Login fails on mobile" in text
        assert "iOS" in text

    def test_no_jira_config_raises(self):
        repo = self._make_repo(None)
        with pytest.raises(ValueError, match="Jira"):
            hu_text_from_jira(
                url="https://acme.atlassian.net/browse/DIA-1",
                org_id="org-1",
                user_id="user-1",
                repo=repo,
            )

    def test_acceptance_criteria_included_when_present(self, monkeypatch):
        repo = self._make_repo(
            {"base_url": "https://acme.atlassian.net", "email": "a@b.com", "token": "tok"}
        )
        payload = {
            "key": "DIA-9",
            "fields": {
                "summary": "Feature X",
                "description": "Do something.",
                "customfield_10016": "Given user is logged in\nWhen they click X\nThen Y happens",
            },
        }
        fake_jira_instance = _FakeJiraForIssue(payload)

        def _fake_client(base_url, email, token):
            c = JiraApiClient.__new__(JiraApiClient)
            c._jira = fake_jira_instance
            return c

        monkeypatch.setattr("src.testplan.jira_source.JiraApiClient", _fake_client)

        text = hu_text_from_jira(
            url="https://acme.atlassian.net/browse/DIA-9",
            org_id="org-1",
            user_id="user-1",
            repo=repo,
        )
        assert "Feature X" in text
        assert "logged in" in text

    def test_bad_url_propagates(self):
        repo = self._make_repo(
            {"base_url": "https://acme.atlassian.net", "email": "a@b.com", "token": "tok"}
        )
        with pytest.raises(ValueError, match="key"):
            hu_text_from_jira(
                url="https://acme.atlassian.net/projects/DIA",
                org_id="org-1",
                user_id="user-1",
                repo=repo,
            )
