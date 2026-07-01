import src.db.pool as poolmod


def test_get_pool_is_singleton(monkeypatch):
    created = []
    class FakePool:
        def __init__(self, *a, **k): created.append(k)
        def open(self, **k): pass
        def close(self): pass
    monkeypatch.setattr(poolmod, "ConnectionPool", FakePool)
    monkeypatch.setattr(poolmod, "_pool", None)
    p1 = poolmod.get_pool(); p2 = poolmod.get_pool()
    assert p1 is p2                       # singleton
    assert len(created) == 1              # se crea una sola vez
    poolmod.close_pool()


def test_configure_sets_dict_row_and_vector(monkeypatch):
    calls = {"vector": 0}
    monkeypatch.setattr(poolmod, "register_vector", lambda conn: calls.__setitem__("vector", calls["vector"]+1))
    class Conn: row_factory = None
    c = Conn()
    poolmod._configure(c)
    from psycopg.rows import dict_row
    assert c.row_factory is dict_row
    assert calls["vector"] == 1
