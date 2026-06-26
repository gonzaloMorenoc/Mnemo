from unittest.mock import MagicMock

from src.ci.github_app import GitHubCodeHost


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


def test_get_file_url_encodes_path():
    session = MagicMock()
    session.get.return_value = _Resp(200, {"content": "", "sha": "s"})
    auth = MagicMock(); auth.installation_token.return_value = "tok"
    host = GitHubCodeHost(auth=auth, installation_id="1", repo_full_name="o/r", session=session)
    host._get_file("tests/a b/spec.ts", "main")
    url = session.get.call_args.args[0] if session.get.call_args.args else session.get.call_args.kwargs.get("url", "")
    url = str(url) + str(session.get.call_args)
    assert "a%20b" in url and "/contents/" in url   # el espacio se codifica, las barras no
