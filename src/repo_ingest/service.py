"""Indexing service — ties list_tree (T1) + TestAssetRepository (T2) together.

Deterministic: no LLM, no external I/O beyond the injected codehost / asset_repo.
"""

import logging
from collections import Counter
from typing import Any, Dict

from src.ci.github_app import is_test_path

_log = logging.getLogger(__name__)

_MAX_FILES = 200
_MAX_BYTES = 100_000

# Noise directory names that should NOT be treated as domain labels.
_NOISE_DIRS = frozenset(
    {"tests", "test", "e2e", "cypress", "specs", "__tests__", "features", "src"}
)

# Noise filename stems that carry no domain information.
_NOISE_STEMS = frozenset({"spec", "test", "index", "main", "app", "utils", "helpers"})


def _framework(path: str) -> str:
    """Infer test framework from the file extension / name pattern."""
    p = path.lower()
    if p.endswith(".feature"):
        return "cucumber"
    if ".cy." in p:
        return "cypress"
    return "playwright"


def _domain(path: str) -> str:
    """Best-effort domain label extracted from the path.

    Strategy:
    1. Walk directory segments (left-to-right), skip noise dirs.
    2. If a meaningful directory is found, return it.
    3. Otherwise fall back to the filename stem (first component before "."),
       unless that stem is itself a noise word — then return "general".
    """
    parts = path.lower().split("/")
    dirs = parts[:-1]
    for d in dirs:
        if d and d not in _NOISE_DIRS:
            return d
    # No meaningful directory → try filename stem
    filename = parts[-1] if parts else ""
    stem = filename.split(".")[0]
    return stem if (stem and stem not in _NOISE_STEMS) else "general"


def index_repo_tests(
    *,
    user_id: str,
    org_id: str,
    repo: str,
    codehost,
    asset_repo,
) -> Dict[str, Any]:
    """Fetch, filter, and index test assets from a repository.

    Args:
        user_id:    Caller's user identifier (forwarded to asset_repo).
        org_id:     Organisation identifier (forwarded to asset_repo).
        repo:       Full repository name, e.g. "acme/frontend".
        codehost:   Object exposing ``list_tree() -> list[str]`` and
                    ``read_file(path) -> str | None``.
        asset_repo: Object exposing
                    ``replace_for_repo(*, user_id, org_id, repo, assets) -> int``.

    Returns:
        ``{"indexed": int, "by_domain": dict[str, int], "skipped": int}``
    """
    all_paths = codehost.list_tree()
    # Detect truncation: codehost may expose it as an attribute set by list_tree.
    truncated: bool = bool(getattr(codehost, "_last_tree_truncated", False))
    if truncated:
        _log.warning("codehost reported a truncated tree for %s — index is partial", repo)

    test_paths = [p for p in all_paths if is_test_path(p)][:_MAX_FILES]

    assets: list[Dict[str, str]] = []
    skipped = 0

    for p in test_paths:
        content = codehost.read_file(p)
        if not content or len(content.encode("utf-8")) > _MAX_BYTES:
            skipped += 1
            continue
        assets.append(
            {
                "path": p,
                "framework": _framework(p),
                "domain": _domain(p),
                "content": content,
            }
        )

    asset_repo.replace_for_repo(
        user_id=user_id,
        org_id=org_id,
        repo=repo,
        assets=assets,
    )

    return {
        "indexed": len(assets),
        "by_domain": dict(Counter(a["domain"] for a in assets)),
        "skipped": skipped,
        "truncated": truncated,
    }
