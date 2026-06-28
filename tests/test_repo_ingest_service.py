"""Tests for src/repo_ingest/service.py — index_repo_tests.

TDD order:
  1. Write tests (RED)
  2. Run → FAIL (service.py doesn't exist yet)
  3. Implement service.py (GREEN)
  4. Refactor + verify caps
"""

import pytest

from src.repo_ingest.service import _domain, _framework, index_repo_tests

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

SMALL_CONTENT = "test content"
BIG_CONTENT = "x" * 100_001  # > 100 000 bytes → must be skipped


class FakeCodeHost:
    """Minimal codehost stub.

    list_tree returns a fixed mix of test paths and non-test paths.
    read_file returns a dict of path→content; missing keys return None.
    """

    def __init__(self, paths: list[str], contents: dict[str, str]):
        self._paths = paths
        self._contents = contents

    def list_tree(self) -> list[str]:
        return list(self._paths)

    def read_file(self, path: str) -> str | None:
        return self._contents.get(path)


class FakeAssetRepo:
    """Captures the call to replace_for_repo."""

    def __init__(self):
        self.calls: list[dict] = []

    def replace_for_repo(self, *, user_id, org_id, repo, assets):
        self.calls.append(
            {"user_id": user_id, "org_id": org_id, "repo": repo, "assets": list(assets)}
        )
        return len(assets)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

_TREE = [
    "e2e/login.spec.ts",       # test  → playwright
    "src/app.ts",              # NOT a test
    "features/billing.feature",  # test → cucumber
    "cypress/smoke.cy.ts",     # test → cypress
    "README.md",               # NOT a test
]

_CONTENTS = {
    "e2e/login.spec.ts": SMALL_CONTENT,
    "features/billing.feature": SMALL_CONTENT,
    "cypress/smoke.cy.ts": SMALL_CONTENT,
}


def _make_codehost(paths=None, contents=None):
    return FakeCodeHost(
        _TREE if paths is None else paths,
        _CONTENTS if contents is None else contents,
    )


def _make_asset_repo():
    return FakeAssetRepo()


# ---------------------------------------------------------------------------
# Unit tests — _framework helper
# ---------------------------------------------------------------------------

class TestFramework:
    def test_feature_is_cucumber(self):
        assert _framework("features/login.feature") == "cucumber"

    def test_cy_is_cypress(self):
        assert _framework("cypress/home.cy.ts") == "cypress"

    def test_spec_ts_is_playwright(self):
        assert _framework("e2e/login.spec.ts") == "playwright"

    def test_test_ts_is_playwright(self):
        assert _framework("tests/auth.test.ts") == "playwright"

    def test_uppercase_feature_normalised(self):
        assert _framework("Features/LOGIN.FEATURE") == "cucumber"


# ---------------------------------------------------------------------------
# Unit tests — _domain helper
# ---------------------------------------------------------------------------

class TestDomain:
    def test_top_level_folder_outside_noise(self):
        # "login" is the first non-noise segment after "e2e/"
        assert _domain("e2e/login.spec.ts") == "login"

    def test_billing_from_features(self):
        assert _domain("features/billing.feature") == "billing"

    def test_deep_path(self):
        assert _domain("e2e/auth/login.spec.ts") == "auth"

    def test_no_meaningful_segment_is_general(self):
        # Only noise segments → general
        assert _domain("tests/spec.ts") == "general"


# ---------------------------------------------------------------------------
# Integration-style test — happy path
# ---------------------------------------------------------------------------

class TestIndexRepoTests:
    def test_filters_to_test_files_only(self):
        codehost = _make_codehost()
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        # 3 test files in _TREE; all have content → indexed = 3
        assert result["indexed"] == 3
        assert result["skipped"] == 0

    def test_replace_for_repo_called_once_with_correct_args(self):
        codehost = _make_codehost()
        asset_repo = _make_asset_repo()

        index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert len(asset_repo.calls) == 1
        call = asset_repo.calls[0]
        assert call["user_id"] == "u1"
        assert call["org_id"] == "org1"
        assert call["repo"] == "acme/repo"
        assert len(call["assets"]) == 3

    def test_framework_inferred_correctly(self):
        codehost = _make_codehost()
        asset_repo = _make_asset_repo()

        index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assets = asset_repo.calls[0]["assets"]
        by_path = {a["path"]: a["framework"] for a in assets}
        assert by_path["e2e/login.spec.ts"] == "playwright"
        assert by_path["features/billing.feature"] == "cucumber"
        assert by_path["cypress/smoke.cy.ts"] == "cypress"

    def test_domain_inferred_from_path(self):
        codehost = _make_codehost()
        asset_repo = _make_asset_repo()

        index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assets = asset_repo.calls[0]["assets"]
        by_path = {a["path"]: a["domain"] for a in assets}
        assert by_path["e2e/login.spec.ts"] == "login"
        assert by_path["features/billing.feature"] == "billing"

    def test_by_domain_in_result(self):
        codehost = _make_codehost()
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert isinstance(result["by_domain"], dict)
        # "login", "billing", "smoke" are expected domains
        assert result["by_domain"].get("login", 0) >= 1
        assert result["by_domain"].get("billing", 0) >= 1

    def test_non_test_paths_excluded(self):
        """src/app.ts and README.md must NOT appear in assets."""
        codehost = _make_codehost()
        asset_repo = _make_asset_repo()

        index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        paths = [a["path"] for a in asset_repo.calls[0]["assets"]]
        assert "src/app.ts" not in paths
        assert "README.md" not in paths

    # -----------------------------------------------------------------------
    # Cap: files with None content are skipped
    # -----------------------------------------------------------------------

    def test_none_content_skipped(self):
        tree = ["e2e/login.spec.ts", "e2e/missing.spec.ts"]
        contents = {"e2e/login.spec.ts": SMALL_CONTENT}  # missing.spec.ts → None
        codehost = _make_codehost(tree, contents)
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert result["indexed"] == 1
        assert result["skipped"] == 1

    # -----------------------------------------------------------------------
    # Cap: files larger than 100 KB are skipped
    # -----------------------------------------------------------------------

    def test_oversized_file_skipped(self):
        tree = ["e2e/login.spec.ts", "e2e/huge.spec.ts"]
        contents = {
            "e2e/login.spec.ts": SMALL_CONTENT,
            "e2e/huge.spec.ts": BIG_CONTENT,  # 100 001 bytes → skip
        }
        codehost = _make_codehost(tree, contents)
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert result["indexed"] == 1
        assert result["skipped"] == 1
        paths = [a["path"] for a in asset_repo.calls[0]["assets"]]
        assert "e2e/huge.spec.ts" not in paths

    # -----------------------------------------------------------------------
    # Cap: list_tree results capped at 200
    # -----------------------------------------------------------------------

    def test_max_files_cap(self):
        # 210 test paths → only first 200 processed
        tree = [f"e2e/test_{i}.spec.ts" for i in range(210)]
        contents = {p: SMALL_CONTENT for p in tree}
        codehost = _make_codehost(tree, contents)
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert result["indexed"] == 200
        assert result["skipped"] == 0
        assert len(asset_repo.calls[0]["assets"]) == 200

    # -----------------------------------------------------------------------
    # Edge: empty repo
    # -----------------------------------------------------------------------

    def test_empty_tree_returns_zero_counts(self):
        codehost = _make_codehost([], {})
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert result == {"indexed": 0, "by_domain": {}, "skipped": 0, "truncated": False}
        # replace_for_repo still called with empty list
        assert asset_repo.calls[0]["assets"] == []

    # -----------------------------------------------------------------------
    # Determinism — no LLM involvement
    # -----------------------------------------------------------------------

    def test_deterministic_two_runs_same_result(self):
        codehost1 = _make_codehost()
        codehost2 = _make_codehost()
        repo1 = _make_asset_repo()
        repo2 = _make_asset_repo()

        r1 = index_repo_tests(user_id="u1", org_id="org1", repo="r",
                              codehost=codehost1, asset_repo=repo1)
        r2 = index_repo_tests(user_id="u1", org_id="org1", repo="r",
                              codehost=codehost2, asset_repo=repo2)

        assert r1 == r2

    # -----------------------------------------------------------------------
    # I1 — truncated flag surfaces in result dict
    # -----------------------------------------------------------------------

    def test_truncated_codehost_sets_flag_in_result(self):
        """When codehost._last_tree_truncated is True after list_tree,
        index_repo_tests must return truncated:True."""

        class TruncatedCodeHost(FakeCodeHost):
            """Simulates a codehost whose list_tree sets _last_tree_truncated."""

            def list_tree(self) -> list[str]:
                paths = super().list_tree()
                self._last_tree_truncated = True  # flag the service reads
                return paths

        codehost = TruncatedCodeHost(_TREE, _CONTENTS)
        asset_repo = _make_asset_repo()

        result = index_repo_tests(
            user_id="u1", org_id="org1", repo="acme/repo",
            codehost=codehost, asset_repo=asset_repo,
        )

        assert result["truncated"] is True
        # Normal indexing still proceeds despite truncation
        assert result["indexed"] == 3
