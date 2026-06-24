from unittest.mock import MagicMock

import pytest

from src.ci.github_app import GitHubCodeHost, GitHubError


def _auth():
    a = MagicMock()
    a.installation_token.return_value = "ghs_tok"
    return a


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_create_issue_posts_and_returns_url():
    posted = {}

    class _Sess:
        def get(self, *a, **k):
            return _Resp(200, {"items": []})  # search vacío

        def post(self, url, json=None, headers=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            return _Resp(201, {"html_url": "https://github.com/o/r/issues/1"})

    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=_Sess())
    url = ch.create_issue(title="T", body="B", labels=["bug"], marker="mnemo:action:a1")
    assert url == "https://github.com/o/r/issues/1"
    assert posted["url"].endswith("/repos/o/r/issues")
    assert "<!-- mnemo:action:a1 -->" in posted["json"]["body"]  # marcador anexado
    assert posted["json"]["labels"] == ["bug"]


def test_create_issue_reuses_when_marker_found():
    class _Sess:
        def get(self, *a, **k):
            return _Resp(200, {"items": [{"html_url": "https://github.com/o/r/issues/5"}]})

        def post(self, *a, **k):
            raise AssertionError("no debe crear si el marcador ya existe")

    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=_Sess())
    assert ch.create_issue(title="T", body="B", labels=[], marker="mnemo:action:a1") \
        == "https://github.com/o/r/issues/5"


def test_create_issue_raises_on_api_error():
    class _Sess:
        def get(self, *a, **k):
            return _Resp(200, {"items": []})

        def post(self, *a, **k):
            return _Resp(422, {})

    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=_Sess())
    with pytest.raises(GitHubError):
        ch.create_issue(title="T", body="B", labels=[], marker="m")


def test_open_draft_pr_not_implemented():
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=MagicMock())
    with pytest.raises(NotImplementedError):
        ch.open_draft_pr(title="t", body="b", patch="p")
