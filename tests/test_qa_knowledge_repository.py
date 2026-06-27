"""
Tests for QaKnowledgeRepository.

Unit tests: mock _connect/cursor so no DB needed.
Integration tests: marked @pytest.mark.integration, run against real prod DB.
"""
import os
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from dotenv import load_dotenv

load_dotenv()

from src.knowledge.repository import QaKnowledgeRepository  # noqa: E402

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
    """Return a (conn_mock, cur_mock) pair configured for membership=member."""
    cur = MagicMock()
    # _is_member → fetchone returns {"ok": member}
    member_row = {"ok": member}
    if fetchone_extra is not None:
        cur.fetchone.side_effect = [member_row, fetchone_extra]
    else:
        cur.fetchone.return_value = member_row
    if fetchall_result is not None:
        cur.fetchall.return_value = fetchall_result

    conn = MagicMock()
    # Support 'with conn.cursor() as cur:' pattern
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx

    # Support 'with self._connect() as conn, conn.cursor() as cur:' pattern
    conn_ctx = MagicMock()
    conn_ctx.__enter__ = MagicMock(return_value=conn)
    conn_ctx.__exit__ = MagicMock(return_value=False)

    return conn_ctx, conn, cur


# ---------------------------------------------------------------------------
# Unit tests — no DATABASE_URL required
# ---------------------------------------------------------------------------

class TestCreateItemValidation:
    def test_invalid_kind_raises_value_error(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        with pytest.raises(ValueError, match="kind inválido"):
            repo.create_item(
                user_id="u", org_id="o", kind="badkind", title="T"
            )

    def test_all_valid_kinds_do_not_raise_on_kind_check(self):
        """Only the ValueError on kind must not fire for valid kinds."""
        valid_kinds = {"regla_negocio", "flujo", "riesgo", "glosario", "leccion", "reto", "patron"}
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        for kind in valid_kinds:
            # Will fail on _connect (dummy URL) but must not raise ValueError for kind
            with pytest.raises(Exception) as exc_info:
                repo.create_item(user_id="u", org_id="o", kind=kind, title="T")
            assert "kind inválido" not in str(exc_info.value)


class TestCreateItemNonMember:
    def test_returns_none_when_not_member(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.create_item(
                user_id="u", org_id="o", kind="flujo", title="T"
            )
        assert result is None


class TestListItemsNonMember:
    def test_returns_empty_list_when_not_member(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.list_items(user_id="u", org_id="o")
        assert result == []


class TestSearchSemanticNonMember:
    def test_returns_empty_list_when_not_member(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.search_semantic(
                user_id="u", org_id="o", query_embedding=[0.1] * 384
            )
        assert result == []


class TestGetItemNonMember:
    def test_returns_none_when_not_member(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.get_item(user_id="u", org_id="o", item_id="some-id")
        assert result is None


class TestCreateItemMember:
    def test_returns_dict_from_cursor(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        returned_row = {
            "id": "abc", "kind": "flujo", "title": "T",
            "domain": None, "tags": [], "confidence": "confirmado",
            "created_at": "2026-01-01",
        }
        conn_ctx, conn, cur = _make_conn_ctx(member=True, fetchone_extra=returned_row)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.create_item(
                user_id="u", org_id="o", kind="flujo", title="T"
            )
        assert result is not None
        assert result["id"] == "abc"
        assert result["kind"] == "flujo"


class TestListItemsMember:
    def test_returns_rows_from_cursor(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        rows = [
            {"id": "1", "kind": "reto", "title": "R1", "challenge": None,
             "approach": None, "outcome": None, "domain": "qa", "tags": [],
             "project": None, "source": "manual", "confidence": "confirmado",
             "created_at": "2026-01-01"},
        ]
        conn_ctx, conn, cur = _make_conn_ctx(member=True, fetchall_result=rows)
        with patch.object(repo, "_connect", return_value=conn_ctx):
            result = repo.list_items(user_id="u", org_id="o")
        assert len(result) == 1
        assert result[0]["id"] == "1"


class TestSearchSemanticMember:
    def test_returns_rows_from_cursor(self):
        repo = QaKnowledgeRepository(db_url="dummy", embedder=FakeEmb())
        rows = [
            {"id": "x", "kind": "flujo", "title": "T", "challenge": None,
             "approach": None, "outcome": None, "domain": None, "confidence": "confirmado"},
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
            (user, f"kn-{user[:8]}@test.internal"),
        )
        conn.commit()
    yield user
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.organizations where created_by=%s", (user,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


@pytest.fixture
def org_with_member(demo_user):
    """Create an org with demo_user as member (via organizations trigger)."""
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "insert into public.organizations (name, created_by) values (%s,%s) returning id",
            (f"kn-org-{demo_user[:8]}", demo_user),
        )
        org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": demo_user, "org_id": org_id}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("delete from public.qa_knowledge where org_id=%s", (org_id,))
        conn.commit()
    # org itself is cleaned up by demo_user fixture via cascade / created_by delete


@pytest.mark.integration
def test_create_and_list_item(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = QaKnowledgeRepository(db_url=DBURL, embedder=FakeEmb())
    item = repo.create_item(
        user_id=u, org_id=o, kind="flujo",
        title="Login flow",
        challenge="User cannot log in after password reset",
        approach="Check token expiry before redirect",
        domain="auth",
        tags=["login", "token"],
    )
    assert item is not None
    assert item["kind"] == "flujo"
    assert item["title"] == "Login flow"

    items = repo.list_items(user_id=u, org_id=o)
    assert any(i["id"] == item["id"] for i in items)


@pytest.mark.integration
def test_list_items_filter_by_kind(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = QaKnowledgeRepository(db_url=DBURL, embedder=FakeEmb())
    repo.create_item(user_id=u, org_id=o, kind="flujo", title="Flow A")
    repo.create_item(user_id=u, org_id=o, kind="riesgo", title="Risk B")

    flujos = repo.list_items(user_id=u, org_id=o, kind="flujo")
    riesgos = repo.list_items(user_id=u, org_id=o, kind="riesgo")
    assert all(i["kind"] == "flujo" for i in flujos)
    assert all(i["kind"] == "riesgo" for i in riesgos)


@pytest.mark.integration
def test_search_semantic_finds_item(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = QaKnowledgeRepository(db_url=DBURL, embedder=FakeEmb())
    item = repo.create_item(
        user_id=u, org_id=o, kind="leccion",
        title="Flaky timeout lesson",
        challenge="Tests timing out under load",
        approach="Add explicit waits",
    )
    assert item is not None

    # Search with the same embedding as the fake embedder would produce
    results = repo.search_semantic(
        user_id=u, org_id=o, query_embedding=[0.1] * 384, k=10
    )
    ids = [r["id"] for r in results]
    assert str(item["id"]) in [str(i) for i in ids]


@pytest.mark.integration
def test_get_item(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    repo = QaKnowledgeRepository(db_url=DBURL, embedder=FakeEmb())
    item = repo.create_item(
        user_id=u, org_id=o, kind="glosario", title="Flakiness"
    )
    assert item is not None
    fetched = repo.get_item(user_id=u, org_id=o, item_id=str(item["id"]))
    assert fetched is not None
    assert fetched["title"] == "Flakiness"


@pytest.mark.integration
def test_non_member_cannot_access(org_with_member):
    u, o = org_with_member["user_id"], org_with_member["org_id"]
    other = str(uuid.uuid4())
    repo = QaKnowledgeRepository(db_url=DBURL, embedder=FakeEmb())
    # create succeeds for member
    item = repo.create_item(user_id=u, org_id=o, kind="patron", title="P")
    assert item is not None

    # non-member gets None / []
    assert repo.create_item(user_id=other, org_id=o, kind="patron", title="P2") is None
    assert repo.list_items(user_id=other, org_id=o) == []
    assert repo.search_semantic(user_id=other, org_id=o, query_embedding=[0.1] * 384) == []
    assert repo.get_item(user_id=other, org_id=o, item_id=str(item["id"])) is None
