from unittest.mock import MagicMock

import pytest

from src.ci.github_app import GitHubCodeHost, GitHubError


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        return self._resp


def _codehost(session):
    auth = MagicMock()
    auth.installation_token.return_value = "tok"
    return GitHubCodeHost(auth=auth, installation_id="1", repo_full_name="o/r", session=session)


def test_publish_check_run_posts_completed_and_returns_url():
    session = _Session(_Resp(201, {"html_url": "https://github.com/o/r/runs/1"}))
    url = _codehost(session).publish_check_run(
        head_sha="abc123", conclusion="failure", title="T", summary="S")
    assert url == "https://github.com/o/r/runs/1"
    body = session.calls[0]["json"]
    assert session.calls[0]["url"].endswith("/repos/o/r/check-runs")
    assert body["name"] == "mnemo/assurance"
    assert body["head_sha"] == "abc123"
    assert body["status"] == "completed"
    assert body["conclusion"] == "failure"
    assert body["output"] == {"title": "T", "summary": "S"}


def test_publish_check_run_raises_on_http_error():
    session = _Session(_Resp(422, {}))
    with pytest.raises(GitHubError):
        _codehost(session).publish_check_run(
            head_sha="abc", conclusion="success", title="T", summary="S")
