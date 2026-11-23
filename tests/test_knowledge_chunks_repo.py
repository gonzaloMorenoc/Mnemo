"""El repositorio de conocimiento guarda fragmentos del texto largo (auditoría
23-nov, #9). Unit: pool y cursor falsos, sin BD."""
from unittest.mock import MagicMock, patch

from src.knowledge.repository import QaKnowledgeRepository

LARGO = " ".join(f"paso{i} del runbook" for i in range(400))


class Cur:
    """Cursor falso: membership y tabla de fragmentos presentes."""

    def __init__(self, row):
        self.row = row
        self.sql = []
        self.many = []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self._last = sql

    def executemany(self, sql, rows):
        self.many.append(list(rows))

    def fetchone(self):
        if "to_regclass" in self._last or "memberships" in self._last:
            return {"ok": True}
        return self.row

    def fetchall(self):
        return []


def _ctx(obj):
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=obj)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def _repo_with(cur):
    conn = MagicMock()
    conn.cursor.return_value = _ctx(cur)
    pool = MagicMock()
    pool.connection.return_value = _ctx(conn)
    emb = MagicMock()
    emb.embed.return_value = [0.0] * 384
    return QaKnowledgeRepository(db_url="postgres://x", embedder=emb), pool


def test_create_long_item_stores_one_embedding_per_chunk():
    cur = Cur({"id": "k1", "kind": "runbook", "title": "T"})
    repo, pool = _repo_with(cur)
    with patch("src.knowledge.repository.get_pool", return_value=pool):
        repo.create_item(user_id="u", org_id="o", kind="runbook", title="T", challenge=LARGO)
    assert len(cur.many) == 1 and len(cur.many[0]) > 1
    assert repo.embedder.embed.call_count == 1 + len(cur.many[0])


def test_create_short_item_stores_no_chunks():
    cur = Cur({"id": "k1", "kind": "runbook", "title": "T"})
    repo, pool = _repo_with(cur)
    with patch("src.knowledge.repository.get_pool", return_value=pool):
        repo.create_item(user_id="u", org_id="o", kind="runbook", title="T", challenge="corto")
    assert cur.many == [] and not any("qa_knowledge_chunks" in s for s in cur.sql)


def test_update_content_replaces_chunks():
    cur = Cur({"id": "k1"})
    repo, pool = _repo_with(cur)
    current = {"id": "k1", "title": "T", "challenge": "c", "approach": None}
    with patch.object(repo, "get_item", return_value=current), \
            patch("src.knowledge.repository.get_pool", return_value=pool):
        repo.update_item(user_id="u", org_id="o", item_id="k1", fields={"challenge": LARGO})
    assert any("delete from public.qa_knowledge_chunks" in s for s in cur.sql)
    assert len(cur.many[0]) > 1


def test_search_uses_chunks_when_table_exists():
    cur = Cur(None)
    repo, pool = _repo_with(cur)
    with patch("src.knowledge.repository.get_pool", return_value=pool):
        repo.search_semantic(user_id="u", org_id="o", query_embedding=[0.0] * 384)
    assert any("qa_knowledge_chunks" in s and "min(dist)" in s for s in cur.sql)
