import pytest

from src.jira.client import JiraApiClient, JiraApiError


class _FakeJira:
    """Imita atlassian.Jira: devuelve 2 páginas y luego vacío."""

    def __init__(self):
        self.url = "https://acme.atlassian.net"
        self._pages = [
            {"total": 3, "issues": [
                {"key": "B-1", "fields": {"summary": "s1", "description": "d1",
                 "issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
                {"key": "B-2", "fields": {"summary": "s2", "description": "d2",
                 "issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
            ]},
            {"total": 3, "issues": [
                {"key": "B-3", "fields": {"summary": "s3", "description": "d3",
                 "issuetype": {"name": "Bug"}, "status": {"name": "Done"}}},
            ]},
        ]

    def jql(self, jql, start=0, limit=50, fields=None):
        idx = 0 if start == 0 else 1
        return self._pages[idx]


def _client_with(fake):
    c = JiraApiClient.__new__(JiraApiClient)
    c._jira = fake
    return c


def test_fetch_bugs_paginates():
    c = _client_with(_FakeJira())
    bugs = c.fetch_bugs("issuetype = Bug", page_size=2)
    assert [b.key for b in bugs] == ["B-1", "B-2", "B-3"]
    assert bugs[0].url == "https://acme.atlassian.net/browse/B-1"


def test_fetch_bugs_respects_max_issues():
    c = _client_with(_FakeJira())
    bugs = c.fetch_bugs("issuetype = Bug", page_size=2, max_issues=1)
    assert len(bugs) == 1


def test_fetch_bugs_wraps_errors():
    class _Boom:
        url = "https://acme.atlassian.net"
        def jql(self, *a, **k):
            raise RuntimeError("401 Unauthorized")
    c = _client_with(_Boom())
    with pytest.raises(JiraApiError):
        c.fetch_bugs("issuetype = Bug")
