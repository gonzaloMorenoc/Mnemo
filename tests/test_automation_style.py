"""Tests for retrieve_style_examples (Task 1 — G5 few-shot retrieval)."""
import pytest

from src.automation.style import retrieve_style_examples

_PATH_A = "e2e/login.spec.ts"
_CONTENT_A = "import {test} from '@playwright/test';\n\ntest('login', async ({ page }) => {\n  await page.goto('/login');\n});"

_PATH_B = "e2e/logout.spec.ts"
_CONTENT_B = "import {test} from '@playwright/test';\n\ntest('logout', async ({ page }) => {\n  await page.click('#logout');\n});"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeEmbedder:
    def embed(self, text: str):
        return [0.0] * 384


class _FakeAssetRepo:
    def __init__(self, rows):
        self._rows = rows
        self.last_call = None

    def search_semantic(self, *, user_id, org_id, query_embedding, k):
        self.last_call = dict(user_id=user_id, org_id=org_id,
                              query_embedding=query_embedding, k=k)
        return self._rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_two_rows_concatenated():
    """2 rows → concatenated with // --- ejemplo: <path> --- headers and \\n\\n between."""
    rows = [
        {"path": _PATH_A, "content": _CONTENT_A},
        {"path": _PATH_B, "content": _CONTENT_B},
    ]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="login flow",
        asset_repo=repo, embedder=embedder, k=3,
    )

    assert result is not None
    block_a = f"// --- ejemplo: {_PATH_A} ---\n{_CONTENT_A}"
    block_b = f"// --- ejemplo: {_PATH_B} ---\n{_CONTENT_B}"
    assert result == f"{block_a}\n\n{block_b}"


def test_search_semantic_forwarded_args():
    """search_semantic is called with the correct user_id, org_id, k, and an embedding list."""
    rows = [{"path": _PATH_A, "content": _CONTENT_A}]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    retrieve_style_examples(
        user_id="u-42", org_id="o-99", case_text="some text",
        asset_repo=repo, embedder=embedder, k=5,
    )

    assert repo.last_call["user_id"] == "u-42"
    assert repo.last_call["org_id"] == "o-99"
    assert repo.last_call["k"] == 5
    assert repo.last_call["query_embedding"] == [0.0] * 384


def test_empty_rows_returns_none():
    """search_semantic → [] → None."""
    repo = _FakeAssetRepo([])
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="anything",
        asset_repo=repo, embedder=embedder,
    )

    assert result is None


def test_none_rows_returns_none():
    """search_semantic → None → None (non-member path)."""
    repo = _FakeAssetRepo(None)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="anything",
        asset_repo=repo, embedder=embedder,
    )

    assert result is None


def test_empty_content_row_skipped():
    """A row with empty content is skipped; only the non-empty row appears."""
    rows = [
        {"path": "e2e/empty.spec.ts", "content": ""},
        {"path": _PATH_A, "content": _CONTENT_A},
    ]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="test",
        asset_repo=repo, embedder=embedder,
    )

    assert result is not None
    assert "e2e/empty.spec.ts" not in result
    assert _PATH_A in result


def test_whitespace_only_content_row_skipped():
    """A row with whitespace-only content is also skipped."""
    rows = [
        {"path": "e2e/ws.spec.ts", "content": "   \n  "},
        {"path": _PATH_B, "content": _CONTENT_B},
    ]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="test",
        asset_repo=repo, embedder=embedder,
    )

    assert result is not None
    assert "e2e/ws.spec.ts" not in result
    assert _PATH_B in result


def test_cap_6000_chars():
    """A row whose block would exceed 6000 chars is not included."""
    big_content = "x" * 9000
    rows = [{"path": "e2e/big.spec.ts", "content": big_content}]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="heavy test",
        asset_repo=repo, embedder=embedder,
    )

    # The block alone (header + 9000-char content) exceeds 6000 → skipped → None
    assert result is None


def test_cap_second_row_excluded_when_over_limit():
    """First row fits; second row would push total past 6000 → second row excluded."""
    # Build a first content that is just under 6000 when wrapped in a block header
    header_a = f"// --- ejemplo: {_PATH_A} ---\n"
    first_content = "a" * (6000 - len(header_a) - 1)  # block exactly 5999 chars
    big_content_b = "b" * 5000  # adding this would exceed 6000

    rows = [
        {"path": _PATH_A, "content": first_content},
        {"path": _PATH_B, "content": big_content_b},
    ]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="cap test",
        asset_repo=repo, embedder=embedder,
    )

    assert result is not None
    assert _PATH_A in result
    assert _PATH_B not in result


def test_all_rows_empty_returns_none():
    """All rows have empty content → None."""
    rows = [
        {"path": "a.spec.ts", "content": ""},
        {"path": "b.spec.ts", "content": None},
    ]
    repo = _FakeAssetRepo(rows)
    embedder = _FakeEmbedder()

    result = retrieve_style_examples(
        user_id="u-1", org_id="o-1", case_text="test",
        asset_repo=repo, embedder=embedder,
    )

    assert result is None
