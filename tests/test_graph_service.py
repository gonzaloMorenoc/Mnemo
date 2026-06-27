"""
Tests for GraphService.build_graph.

Unit tests: mock _connect/cursor so no DB needed.
Integration tests: marked @pytest.mark.integration, run against real prod DB.
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from src.graph.service import GraphService


# ---------------------------------------------------------------------------
# Helpers to build cursor/conn mocks — mirror knowledge/repository test pattern
# ---------------------------------------------------------------------------

def _make_conn_ctx(member: bool, fetchall_results: list = None):
    """
    Return (conn_ctx, conn, cur) configured for membership=member.

    fetchall_results: list of lists, consumed sequentially by cur.fetchall()
    calls.  The first fetchall() call after the membership fetchone() gets
    fetchall_results[0], the second gets fetchall_results[1], etc.
    """
    cur = MagicMock()
    # _is_member → fetchone returns {"ok": member}
    cur.fetchone.return_value = {"ok": member}

    if fetchall_results is not None:
        cur.fetchall.side_effect = list(fetchall_results)
    else:
        cur.fetchall.return_value = []

    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx

    conn_ctx = MagicMock()
    conn_ctx.__enter__ = MagicMock(return_value=conn)
    conn_ctx.__exit__ = MagicMock(return_value=False)

    return conn_ctx, conn, cur


# Shared test data
K1_ID = "k1-0000-0000-0000-000000000001"
K2_ID = "k2-0000-0000-0000-000000000002"
F1_ID = "f1-0000-0000-0000-000000000003"
SHARED_TAG = "regression"

KNOWLEDGE_ROWS = [
    {
        "id": K1_ID,
        "kind": "flujo",
        "title": "Login flow",
        "domain": "facturacion",
        "tags": [SHARED_TAG, "auth"],
        "defect_family_id": F1_ID,
    },
    {
        "id": K2_ID,
        "kind": "riesgo",
        "title": "Payment risk",
        "domain": "facturacion",
        "tags": [SHARED_TAG],
        "defect_family_id": None,
    },
]

DEFECT_ROWS = [
    {
        "id": F1_ID,
        "title": "NullPointer in login",
        "occurrence_count": 5,
    },
]


# ---------------------------------------------------------------------------
# Unit tests — no DATABASE_URL required
# ---------------------------------------------------------------------------

class TestBuildGraphNonMember:
    def test_returns_empty_when_not_member(self):
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(member=False)
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o")
        assert result == {"nodes": [], "edges": []}


class TestBuildGraphNodeCounts:
    def test_two_knowledge_one_defect_one_domain(self):
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o")

        nodes = result["nodes"]
        by_type = {}
        for n in nodes:
            by_type.setdefault(n["type"], []).append(n)

        assert len(by_type.get("knowledge", [])) == 2, f"Expected 2 knowledge nodes, got {by_type}"
        assert len(by_type.get("defect", [])) == 1, f"Expected 1 defect node, got {by_type}"
        assert len(by_type.get("domain", [])) == 1, f"Expected 1 domain node, got {by_type}"


class TestBuildGraphEdges:
    def test_documenta_edge_knowledge_to_defect(self):
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o")

        documenta = [e for e in result["edges"] if e["relation"] == "documenta"]
        assert len(documenta) == 1
        assert documenta[0]["source"] == K1_ID
        assert documenta[0]["target"] == F1_ID

    def test_pertenece_edges_knowledge_to_domain(self):
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o")

        pertenece = [e for e in result["edges"] if e["relation"] == "pertenece"]
        assert len(pertenece) == 2
        sources = {e["source"] for e in pertenece}
        assert K1_ID in sources
        assert K2_ID in sources

    def test_tag_edge_between_knowledge_sharing_tag(self):
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o")

        tag_edges = [e for e in result["edges"] if e["relation"] == "tag"]
        assert len(tag_edges) == 1
        pair = {tag_edges[0]["source"], tag_edges[0]["target"]}
        assert pair == {K1_ID, K2_ID}


class TestBuildGraphLimit:
    def test_limit_trims_rows(self):
        """When limit=1 only the first knowledge row is used → 1 knowledge node."""
        svc = GraphService(db_url="dummy")
        # With limit=1 the SQL returns only 1 row; mock that
        single_row = [KNOWLEDGE_ROWS[0]]
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[single_row, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o", limit=1)

        knowledge_nodes = [n for n in result["nodes"] if n["type"] == "knowledge"]
        assert len(knowledge_nodes) == 1
        assert knowledge_nodes[0]["id"] == K1_ID

        # Verify limit was passed to execute as second param
        calls = cur.execute.call_args_list
        # First call is _is_member, second is the knowledge query
        knowledge_call = calls[1]
        assert knowledge_call[0][1][1] == 1  # limit param


class TestBuildGraphFocus:
    def test_focus_keeps_only_node_and_neighbors(self):
        """focus=K2_ID should keep K2, domain:facturacion, and tag-neighbor K1."""
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o", focus=K2_ID)

        node_ids = {n["id"] for n in result["nodes"]}
        # K2 itself must be present
        assert K2_ID in node_ids
        # Its domain neighbor
        assert "domain:facturacion" in node_ids
        # K1 is connected via tag edge
        assert K1_ID in node_ids
        # F1 is NOT a neighbor of K2 (only K1→F1)
        assert F1_ID not in node_ids

    def test_focus_keeps_only_relevant_edges(self):
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o", focus=K2_ID)

        # documenta edge K1→F1 is excluded (F1 not in keep set)
        documenta = [e for e in result["edges"] if e["relation"] == "documenta"]
        assert len(documenta) == 0

    def test_focus_on_knowledge_with_defect(self):
        """focus=K1_ID should keep K1, F1, domain:facturacion, and K2 (tag neighbor)."""
        svc = GraphService(db_url="dummy")
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[KNOWLEDGE_ROWS, DEFECT_ROWS],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o", focus=K1_ID)

        node_ids = {n["id"] for n in result["nodes"]}
        assert K1_ID in node_ids
        assert F1_ID in node_ids
        assert "domain:facturacion" in node_ids
        # K2 connected via tag
        assert K2_ID in node_ids


class TestBuildGraphNoDefectFamilies:
    def test_no_defect_families_when_no_fam_ids(self):
        """When no knowledge has defect_family_id, second fetchall never called."""
        svc = GraphService(db_url="dummy")
        rows_no_fam = [
            {
                "id": K2_ID,
                "kind": "riesgo",
                "title": "Payment risk",
                "domain": "facturacion",
                "tags": [],
                "defect_family_id": None,
            }
        ]
        conn_ctx, conn, cur = _make_conn_ctx(
            member=True,
            fetchall_results=[rows_no_fam],
        )
        with patch.object(svc, "_connect", return_value=conn_ctx):
            result = svc.build_graph(user_id="u", org_id="o")

        knowledge_nodes = [n for n in result["nodes"] if n["type"] == "knowledge"]
        defect_nodes = [n for n in result["nodes"] if n["type"] == "defect"]
        assert len(knowledge_nodes) == 1
        assert len(defect_nodes) == 0
        # Second execute (defect families query) should NOT have been called
        assert cur.execute.call_count == 2  # membership + knowledge only
