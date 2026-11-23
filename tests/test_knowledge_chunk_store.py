"""Persistencia y búsqueda por fragmentos (auditoría 23-nov, #9). Unit, sin BD:
cursor falso que registra el SQL."""
from src.knowledge.chunk_store import (
    chunk_embeddings,
    chunks_table_exists,
    replace_chunks,
    search_sql,
)


class FakeCursor:
    def __init__(self, table_exists=True):
        self.table_exists = table_exists
        self.executed = []
        self.many = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def executemany(self, sql, rows):
        self.many.append((sql, list(rows)))

    def fetchone(self):
        return {"ok": self.table_exists}


class CountingEmbedder:
    def __init__(self):
        self.n = 0

    def embed(self, text):
        self.n += 1
        return [0.1] * 384


def test_short_items_embed_nothing_extra():
    emb = CountingEmbedder()
    assert chunk_embeddings(emb, "t", "corto", None) == []
    assert emb.n == 0


def test_long_items_embed_every_chunk():
    emb = CountingEmbedder()
    out = chunk_embeddings(emb, "t", " ".join(["palabra"] * 300), None)
    assert len(out) == emb.n and emb.n > 1


def test_replace_deletes_then_inserts_with_index_and_org():
    cur = FakeCursor()
    n = replace_chunks(cur, knowledge_id="k1", org_id="o1", embeddings=[[0.1] * 384, [0.2] * 384])
    assert n == 2
    assert any("delete from public.qa_knowledge_chunks" in s for s, _ in cur.executed)
    _, rows = cur.many[0]
    assert [(r[0], r[1], r[2]) for r in rows] == [("k1", "o1", 0), ("k1", "o1", 1)]


def test_replace_is_a_noop_without_the_table():
    """Código desplegado antes de aplicar la migración 033: no rompe la escritura."""
    cur = FakeCursor(table_exists=False)
    assert replace_chunks(cur, knowledge_id="k1", org_id="o1", embeddings=[[0.1] * 384]) == 0
    assert not cur.many and all("delete" not in s for s, _ in cur.executed)


def test_table_check_tolerates_unexpected_rows():
    class Odd(FakeCursor):
        def fetchone(self):
            return None
    assert chunks_table_exists(Odd()) is False


def test_search_sql_aggregates_min_distance_per_item_and_keeps_guards():
    sql = " ".join(search_sql(with_chunks=True).split()).lower()
    assert "qa_knowledge_chunks" in sql and "min(" in sql and "group by" in sql
    assert "status = 'activo'" in sql and "%(org)s" in sql
    legacy = " ".join(search_sql(with_chunks=False).split()).lower()
    assert "qa_knowledge_chunks" not in legacy and "status = 'activo'" in legacy
    assert " as dist" in sql and " as dist" in legacy
