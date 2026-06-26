from unittest.mock import MagicMock
import base64

from src.actions.base import NullCodeHost
from src.ci.github_app import GitHubCodeHost


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
    def json(self):
        return self._payload


def _host(session):
    auth = MagicMock(); auth.installation_token.return_value = "tok"
    return GitHubCodeHost(auth=auth, installation_id="1", repo_full_name="o/r", session=session)


def test_null_codehost_read_file_returns_none():
    assert NullCodeHost().read_file("any.ts") is None


def test_github_read_file_returns_content():
    session = MagicMock()
    # _default_branch() → session.get(repo endpoint) → 200 {"default_branch": "main"}
    # _get_file()       → session.get(contents endpoint) → 200 {"content": ..., "sha": ...}
    content_b64 = base64.b64encode(b"const x = 1;").decode()
    session.get.side_effect = [
        _Resp(200, {"default_branch": "main"}),         # repo metadata (_default_branch)
        _Resp(200, {"content": content_b64, "sha": "s"}),  # contents (_get_file)
    ]
    host = _host(session)
    assert host.read_file("tests/a.spec.ts") == "const x = 1;"


def test_github_read_file_returns_none_on_error():
    session = MagicMock()
    session.get.side_effect = [_Resp(200, {"default_branch": "main"}), _Resp(404)]
    assert _host(session).read_file("missing.ts") is None
