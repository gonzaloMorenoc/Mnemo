"""Fase 1 curación: editar/borrar/obsoletar + exclusión de obsoletos en los read-paths.

Unit (sin BD): mock del pool; se valida la FORMA del SQL (autoridad, updated_at,
re-embedding condicional) y los guards de `status = 'activo'` en cada read-path
(lección de #80: el filtro olvidado en un solo sitio = fuga silenciosa al RAG).
"""
from unittest.mock import MagicMock, patch

import pytest

from src.knowledge.repository import QaKnowledgeRepository


def _fake_pool(conn_ctx):
    pool = MagicMock()
    pool.connection.return_value = conn_ctx
    return pool


def _conn_ctx(cur):
    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


CURRENT = {"id": "k1", "kind": "leccion", "title": "T", "challenge": "C", "approach": "A",
           "outcome": None, "domain": None, "tags": [], "project": None, "source": "manual",
           "confidence": "confirmado", "defect_family_id": None, "run_id": None,
           "created_by": "u1", "created_at": None}


def _repo():
    embedder = MagicMock()
    embedder.embed.return_value = [0.0] * 384
    return QaKnowledgeRepository(db_url="postgres://x", embedder=embedder)


def _all_sql(cur) -> str:
    return " ".join(str(c.args[0]) for c in cur.execute.call_args_list)


# ---------------------------------------------------------------------------
# update_item
# ---------------------------------------------------------------------------

class TestUpdateItem:
    def _run(self, fields, current=CURRENT, row_after=CURRENT):
        repo = _repo()
        cur = MagicMock()
        cur.fetchone.return_value = dict(row_after) if row_after else None
        with patch.object(repo, "get_item", return_value=dict(current) if current else None):
            with patch("src.knowledge.repository.get_pool",
                       return_value=_fake_pool(_conn_ctx(cur))):
                out = repo.update_item(user_id="u1", org_id="o1", item_id="k1", fields=fields)
        return out, repo, cur

    def test_recomputes_embedding_when_content_changes(self):
        out, repo, cur = self._run({"title": "Nuevo título"})
        repo.embedder.embed.assert_called_once()
        text = repo.embedder.embed.call_args.args[0]
        assert "Nuevo título" in text and "C" in text and "A" in text  # merge con lo actual
        assert "embedding=%s" in _all_sql(cur)

    def test_metadata_only_does_not_recompute_embedding(self):
        out, repo, cur = self._run({"domain": "pagos"})
        repo.embedder.embed.assert_not_called()
        assert "embedding=%s" not in _all_sql(cur)

    def test_sql_has_authority_and_updated_at(self):
        _, _, cur = self._run({"title": "x"})
        sql = _all_sql(cur)
        assert "created_by=%s" in sql                 # el autor puede editar lo suyo
        assert "('owner','admin')" in sql             # owner/admin cualquier item
        assert "updated_at=now()" in sql

    def test_returns_none_when_no_permission(self):
        out, _, _ = self._run({"title": "x"}, row_after=None)
        assert out is None

    def test_item_not_found_returns_none_without_update(self):
        out, _, cur = self._run({"title": "x"}, current=None)
        assert out is None
        cur.execute.assert_not_called()

    def test_invalid_status_raises(self):
        repo = _repo()
        with pytest.raises(ValueError):
            repo.update_item(user_id="u", org_id="o", item_id="k",
                             fields={"status": "borrado"})

    def test_invalid_kind_raises(self):
        repo = _repo()
        with pytest.raises(ValueError):
            repo.update_item(user_id="u", org_id="o", item_id="k", fields={"kind": "nope"})

    def test_empty_fields_raises(self):
        repo = _repo()
        with pytest.raises(ValueError):
            repo.update_item(user_id="u", org_id="o", item_id="k", fields={})


# ---------------------------------------------------------------------------
# delete_item
# ---------------------------------------------------------------------------

class TestDeleteItem:
    def _run(self, rowcount):
        repo = _repo()
        cur = MagicMock()
        cur.rowcount = rowcount
        with patch("src.knowledge.repository.get_pool",
                   return_value=_fake_pool(_conn_ctx(cur))):
            ok = repo.delete_item(user_id="u1", org_id="o1", item_id="k1")
        return ok, cur

    def test_delete_true_and_authority_clause(self):
        ok, cur = self._run(rowcount=1)
        assert ok is True
        sql = _all_sql(cur)
        assert "delete from public.qa_knowledge" in sql
        assert "created_by=%s" in sql and "('owner','admin')" in sql

    def test_delete_false_when_no_permission(self):
        ok, _ = self._run(rowcount=0)
        assert ok is False


# ---------------------------------------------------------------------------
# Guards: los read-paths excluyen status='obsoleto' (y el hojeo NO)
# ---------------------------------------------------------------------------

class TestObsoletoExcludedFromReadPaths:
    def test_search_semantic_filters_activo(self):
        repo = _repo()
        cur = MagicMock()
        cur.fetchone.return_value = {"ok": True}
        cur.fetchall.return_value = []
        with patch("src.knowledge.repository.get_pool",
                   return_value=_fake_pool(_conn_ctx(cur))):
            repo.search_semantic(user_id="u", org_id="o", query_embedding=[0.0] * 384)
        assert "status = 'activo'" in _all_sql(cur)

    def test_gaps_sql_constants_filter_activo(self):
        from src.graph import gaps
        for name in ("_SQL_DEFECTO_SIN_CONOCIMIENTO", "_SQL_DOMINIO_SIN_LECCION",
                     "_SQL_RIESGO_SIN_MITIGACION", "_SQL_REGLA_SIN_TEST"):
            assert "status = 'activo'" in getattr(gaps, name), f"{name} sin filtro de status"

    def test_proposal_candidates_filter_activo(self):
        from src.knowledge.proposal_repository import _CANDIDATE_WHERE
        # lección obsoleta → la familia vuelve a ser candidata de auto-propuesta
        assert "status = 'activo'" in _CANDIDATE_WHERE

    def test_build_graph_filters_activo(self):
        from src.graph.service import GraphService
        svc = GraphService(db_url="postgres://x")
        cur = MagicMock()
        cur.fetchone.return_value = {"ok": True}
        cur.fetchall.return_value = []
        with patch("src.graph.service.get_pool", return_value=_fake_pool(_conn_ctx(cur))):
            svc.build_graph(user_id="u", org_id="o")
        assert "status = 'activo'" in _all_sql(cur)

    def test_list_items_shows_all_statuses_by_default(self):
        repo = _repo()
        cur = MagicMock()
        cur.fetchone.return_value = {"ok": True}
        cur.fetchall.return_value = []
        with patch("src.knowledge.repository.get_pool",
                   return_value=_fake_pool(_conn_ctx(cur))):
            repo.list_items(user_id="u", org_id="o")
        sql = _all_sql(cur)
        assert "and status=%s" not in sql        # hojeo: sin filtro implícito
        assert "status" in sql                   # pero la columna se devuelve

    def test_list_items_filters_by_status_and_project(self):
        repo = _repo()
        cur = MagicMock()
        cur.fetchone.return_value = {"ok": True}
        cur.fetchall.return_value = []
        with patch("src.knowledge.repository.get_pool",
                   return_value=_fake_pool(_conn_ctx(cur))):
            repo.list_items(user_id="u", org_id="o", status="obsoleto", project="web")
        sql = _all_sql(cur)
        assert "and status=%s" in sql and "and project=%s" in sql
