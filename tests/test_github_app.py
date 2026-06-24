import base64
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


REPO = "o/r"


class _PrResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _PrSess:
    """Enruta las llamadas de open_draft_pr; registra para aserciones."""

    def __init__(self, *, content="page.locator('#old')", existing_pr=None):
        self.content = content
        self.existing_pr = existing_pr
        self.put_body = None
        self.pr_body = None

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/pulls"):
            return _PrResp(200, [{"html_url": self.existing_pr}] if self.existing_pr else [])
        if url.endswith(f"/repos/{REPO}"):
            return _PrResp(200, {"default_branch": "main"})
        if "/git/ref/heads/" in url:
            return _PrResp(200, {"object": {"sha": "base123"}})
        if "/contents/" in url:
            enc = base64.b64encode(self.content.encode("utf-8")).decode("utf-8")
            return _PrResp(200, {"content": enc, "sha": "filesha"})
        return _PrResp(404, {})

    def post(self, url, json=None, headers=None, timeout=None):
        if url.endswith("/git/refs"):
            return _PrResp(201, {})
        if url.endswith("/pulls"):
            self.pr_body = json
            return _PrResp(201, {"html_url": "https://github.com/o/r/pull/7"})
        return _PrResp(404, {})

    def put(self, url, json=None, headers=None, timeout=None):
        self.put_body = json
        return _PrResp(200, {"commit": {"sha": "c1"}})


def test_open_draft_pr_creates_pr_and_returns_url():
    sess = _PrSess(content="await page.locator('#old').click()")
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    url = ch.open_draft_pr(title="Self-heal", body="B", file_path="t.spec.ts",
                           old_str="locator('#old')", new_str="getByTestId('save')",
                           marker="mnemo:action:a1")
    assert url == "https://github.com/o/r/pull/7"
    # el commit lleva el contenido con el locator reemplazado
    new_content = base64.b64decode(sess.put_body["content"]).decode("utf-8")
    assert "getByTestId('save')" in new_content and "locator('#old')" not in new_content
    # PR draft, head = branch determinista, marcador en el body
    assert sess.pr_body["draft"] is True
    assert sess.pr_body["head"] == "mnemo/self-heal/a1"
    assert "<!-- mnemo:action:a1 -->" in sess.pr_body["body"]


def test_open_draft_pr_reuses_existing_pr():
    sess = _PrSess(existing_pr="https://github.com/o/r/pull/3")
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    url = ch.open_draft_pr(title="T", body="B", file_path="t.spec.ts",
                           old_str="x", new_str="y", marker="mnemo:action:a1")
    assert url == "https://github.com/o/r/pull/3"
    assert sess.put_body is None  # no commit: reusó el PR


def test_open_draft_pr_returns_none_when_locator_absent():
    sess = _PrSess(content="no hay locator aquí")
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    out = ch.open_draft_pr(title="T", body="B", file_path="t.spec.ts",
                           old_str="locator('#missing')", new_str="y", marker="mnemo:action:a1")
    assert out is None
    assert sess.pr_body is None  # no abrió PR


def test_open_draft_pr_raises_on_api_error():
    class _Boom(_PrSess):
        def get(self, url, params=None, headers=None, timeout=None):
            if url.endswith(f"/repos/{REPO}"):
                return _PrResp(500, {})
            return super().get(url, params=params, headers=headers, timeout=timeout)
    sess = _Boom()
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    with pytest.raises(GitHubError):
        ch.open_draft_pr(title="T", body="B", file_path="t.spec.ts",
                         old_str="locator('#old')", new_str="y", marker="mnemo:action:a1")
