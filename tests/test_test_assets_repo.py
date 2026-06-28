"""
Tests for TestAssetRepository.

Unit tests: mock _connect so no DB needed.
Integration tests: marked @pytest.mark.integration, run against real prod DB.
"""
import os
import uuid
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.repo_ingest.repository import TestAssetRepository  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


# ---------------------------------------------------------------------------
# Fake embedder (no HuggingFace loading)
# ---------------------------------------------------------------------------

class FakeEmb:
    def embed(self, text: str):
        return [0.1] * 384


# ---------------------------------------------------------------------------
# Helpers to build cursor/conn mocks
# ---------------------------------------------------------------------------

def _make_conn_ctx(member: bool, fetchone_extra=None, fetchall_result=None):
    """Return a (conn_ctx, conn, cur) triple configured for membership=member."""
    cur = MagicMock()
    member_row = {"ok": member}
    if fetchone_extra is not None:
        cur.fetchone.side_effect = [member_row, fetchone_extra]
    else:
        cur.fetchone.return_value = member_row
    if fetchall_result is not None:
        cur.fetchall.return_value = fetchall_result

    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx

    conn_ctx = MagicMock()
    conn_ctx.__enter__ = MagicMock(return_value=conn)
    conn_ctx.__exit__ = MagicMock(return_value=False)

    return conn_ctx, conn, cur


# ---------------------------------------------------------------------------
# Unit tests — no DATABASE_URL required
# ---------------------------------------------------------------------------

class TestReplaceForRepoNonMember:
    def test_returns_zero_when_not_member(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.replace_for_repo(
                user_id="u", org_id="o", repo="org/repo",
                assets=[{"path": "test_foo.py", "content": "def test_foo(): pass"}],
            )
        assert result == 0

    def test_no_db_write_when_not_member(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            repo.replace_for_repo(
                user_id="u", org_id="o", repo="org/repo",
                assets=[{"path": "t.py", "content": "x"}],
            )
        # execute called only once (the _is_member check); no insert/delete
        assert cur.execute.call_count == 1


class TestReplaceForRepoMember:
    def test_returns_insert_count(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=True)
        assets = [
            {"path": "tests/test_a.py", "framework": "pytest", "domain": "auth",
             "content": "def test_a(): pass"},
            {"path": "tests/test_b.py", "framework": "pytest", "domain": "auth",
             "content": "def test_b(): pass"},
        ]
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.replace_for_repo(
                user_id="u", org_id="o", repo="org/repo", assets=assets,
            )
        assert result == 2

    def test_delete_called_before_insert(self):
        """replace_for_repo must delete the old rows before inserting new ones."""
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=True)
        assets = [{"path": "t.py", "content": "x"}]
        with patch.object(repo, "_connect", return_value=conn_ctx):
            repo.replace_for_repo(
                user_id="u", org_id="o", repo="org/repo", assets=assets,
            )
        calls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        # first call = _is_member, second = delete, third = insert
        assert any("delete" in c for c in calls)
        assert any("insert" in c for c in calls)
        delete_pos = next(i for i, c in enumerate(calls) if "delete" in c)
        insert_pos = next(i for i, c in enumerate(calls) if "insert" in c)
        assert delete_pos < insert_pos

    def test_empty_assets_returns_zero(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=True)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.replace_for_repo(
                user_id="u", org_id="o", repo="org/repo", assets=[],
            )
        assert result == 0


class TestListAssetsNonMember:
    def test_returns_empty_list_when_not_member(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.list_assets(user_id="u", org_id="o")
        assert result == []


class TestListAssetsMember:
    def test_returns_rows_from_cursor(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        rows = [
            {"id": "1", "repo_full_name": "org/repo", "path": "t.py",
             "framework": "pytest", "domain": "auth", "created_at": "2026-01-01"},
        ]
        conn_ctx, conn, cur = _make_conn_ctx(member=True, fetchall_result=rows)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.list_assets(user_id="u", org_id="o")
        assert len(result) == 1
        assert result[0]["id"] == "1"


class TestSearchSemanticNonMember:
    def test_returns_empty_list_when_not_member(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.search_semantic(
                user_id="u", org_id="o", query_embedding=[0.1] * 384
            )
        assert result == []


class TestSearchSemanticMember:
    def test_returns_rows_from_cursor(self):
        repo = TestAssetRepository(db_url="dummy", embedder=FakeEmb())
        rows = [
            {"id": "x", "repo_full_name": "org/repo", "path": "t.py",
             "framework": "pytest", "domain": "auth", "content": "def test_x(): pass"},
        ]
        conn_ctx, conn, cur = _make_conn_ctx(member=True, fetchall_result=rows)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.search_semantic(
                user_id="u", org_id="o", query_embedding=[0.1] * 384
            )
        assert len(result) == 1
        assert result[0]["id"] == "x"


# ---------------------------------------------------------------------------
# Integration tests — require DATABASE_URL + real DB
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_user():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into auth.users (id, email, role, aud, created_at, updated_at)"
            " values (%s,%s,'authenticated','authenticated',now(),now())",
            (user, f"ta-{user[:8]}@test.internal"),
        )
        conn.commit()
    yield user
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where created_by=%s", (user,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


@pytest.fixture
def org_with_member(demo_user):
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into public.organizations (name, created_by) values (%s,%s) returning id",
            (f"ta-org-{demo_user[:8]}", demo_user),
        )
        org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": demo_user, "org_id": org_id}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.test_assets where org_id=%s", (org_id,))
        conn.commit()


@pytest.mark.integration
def test_replace_for_repo_inserts(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())
    assets = [
        {"path": "tests/test_login.py", "framework": "pytest",
         "domain": "auth", "content": "def test_login(): assert True"},
        {"path": "tests/test_signup.py", "framework": "pytest",
         "domain": "auth", "content": "def test_signup(): assert True"},
    ]
    count = repo.replace_for_repo(user_id=u, org_id=o, repo="org/myrepo", assets=assets)
    assert count == 2

    listed = repo.list_assets(user_id=u, org_id=o)
    paths = [r["path"] for r in listed]
    assert "tests/test_login.py" in paths
    assert "tests/test_signup.py" in paths


@pytest.mark.integration
def test_replace_for_repo_deletes_old_rows(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())
    repo.replace_for_repo(
        user_id=u, org_id=o, repo="org/myrepo",
        assets=[{"path": "old.py", "content": "old"}],
    )
    # Replace with a different set — old row must disappear
    count = repo.replace_for_repo(
        user_id=u, org_id=o, repo="org/myrepo",
        assets=[{"path": "new.py", "content": "new"}],
    )
    assert count == 1
    listed = repo.list_assets(user_id=u, org_id=o)
    paths = [r["path"] for r in listed]
    assert "old.py" not in paths
    assert "new.py" in paths


@pytest.mark.integration
def test_non_member_cannot_replace_or_list(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    other = str(uuid.uuid4())
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())
    # member inserts
    repo.replace_for_repo(
        user_id=u, org_id=o, repo="org/r",
        assets=[{"path": "t.py", "content": "x"}],
    )
    # non-member gets 0 / []
    assert repo.replace_for_repo(
        user_id=other, org_id=o, repo="org/r",
        assets=[{"path": "evil.py", "content": "x"}],
    ) == 0
    assert repo.list_assets(user_id=other, org_id=o) == []
    assert repo.search_semantic(
        user_id=other, org_id=o, query_embedding=[0.1] * 384
    ) == []


@pytest.mark.integration
def test_search_semantic_returns_results(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = TestAssetRepository(db_url=DBURL, embedder=FakeEmb())
    repo.replace_for_repo(
        user_id=u, org_id=o, repo="org/r",
        assets=[{"path": "t.py", "framework": "pytest",
                 "domain": "auth", "content": "def test_auth(): pass"}],
    )
    results = repo.search_semantic(
        user_id=u, org_id=o, query_embedding=[0.1] * 384, k=5
    )
    assert len(results) >= 1
    assert results[0]["path"] == "t.py"
