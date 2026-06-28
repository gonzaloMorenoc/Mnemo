"""Tests para GitHubCodeHost.list_tree + is_test_path."""
from unittest.mock import MagicMock

import pytest

from src.ci.github_app import GitHubCodeHost, GitHubError, is_test_path


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _host(session):
    auth = MagicMock()
    auth.installation_token.return_value = "tok"
    return GitHubCodeHost(auth=auth, installation_id="1", repo_full_name="o/r", session=session)


# ---------------------------------------------------------------------------
# list_tree
# ---------------------------------------------------------------------------

def test_list_tree_gets_trees_endpoint_with_recursive():
    """list_tree hace GET a /git/trees/{sha}?recursive=1."""
    session = MagicMock()
    sha = "abc123"
    tree_payload = {
        "tree": [
            {"path": "src/app.ts", "type": "blob"},
            {"path": "tests/login.spec.ts", "type": "blob"},
            {"path": "some/dir", "type": "tree"},  # debe filtrarse
        ]
    }
    session.get.side_effect = [
        _Resp(200, {"default_branch": "main"}),       # _default_branch
        _Resp(200, {"object": {"sha": sha}}),          # _ref_sha
        _Resp(200, tree_payload),                      # trees endpoint
    ]
    host = _host(session)
    result = host.list_tree()

    # Verificar que el tercer GET fue al endpoint correcto con recursive=1
    trees_call = session.get.call_args_list[2]
    assert f"/repos/o/r/git/trees/{sha}" in trees_call[0][0]
    assert trees_call[1]["params"]["recursive"] == "1"


def test_list_tree_returns_only_blob_paths():
    """list_tree devuelve únicamente los path de type=='blob'."""
    session = MagicMock()
    tree_payload = {
        "tree": [
            {"path": "src/app.ts", "type": "blob"},
            {"path": "tests/login.spec.ts", "type": "blob"},
            {"path": "e2e", "type": "tree"},          # directorio, excluir
            {"path": ".github/workflows", "type": "tree"},  # directorio, excluir
            {"path": "features/auth.feature", "type": "blob"},
        ]
    }
    session.get.side_effect = [
        _Resp(200, {"default_branch": "main"}),
        _Resp(200, {"object": {"sha": "deadbeef"}}),
        _Resp(200, tree_payload),
    ]
    result = _host(session).list_tree()
    assert result == ["src/app.ts", "tests/login.spec.ts", "features/auth.feature"]


def test_list_tree_raises_on_non_2xx():
    """list_tree lanza GitHubError si la API devuelve ≥ 300."""
    session = MagicMock()
    session.get.side_effect = [
        _Resp(200, {"default_branch": "main"}),
        _Resp(200, {"object": {"sha": "sha1"}}),
        _Resp(403),
    ]
    with pytest.raises(GitHubError):
        _host(session).list_tree()


def test_list_tree_empty_tree():
    """list_tree devuelve lista vacía cuando el tree no tiene blobs."""
    session = MagicMock()
    session.get.side_effect = [
        _Resp(200, {"default_branch": "main"}),
        _Resp(200, {"object": {"sha": "sha1"}}),
        _Resp(200, {"tree": []}),
    ]
    assert _host(session).list_tree() == []


# ---------------------------------------------------------------------------
# is_test_path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "e2e/login.spec.ts",
    "tests/x.test.ts",
    "features/a.feature",
    "cypress/b.cy.ts",
    "src/__tests__/utils.ts",
    "specs/payment.spec.js",
    "test/helpers.js",
])
def test_is_test_path_accepts_test_paths(path):
    assert is_test_path(path) is True, f"Debería aceptar: {path}"


@pytest.mark.parametrize("path", [
    "src/app.ts",
    "README.md",
    "package.json",
    "src/utils/helper.ts",
    "docs/architecture.md",
])
def test_is_test_path_rejects_non_test_paths(path):
    assert is_test_path(path) is False, f"Debería rechazar: {path}"
