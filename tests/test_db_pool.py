import os

import pytest
from dotenv import load_dotenv

load_dotenv()

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


@pytest.mark.integration
def test_pooled_connection_does_not_leak_claims():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not configured")
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    pool = ConnectionPool(conninfo=url, min_size=1, max_size=1, open=True, kwargs={"row_factory": dict_row})
    try:
        with pool.connection() as c1:
            c1.execute("select set_config('request.jwt.claim.sub', 'user-A', true)")
            # is_local=true → scoped to this transaction; commit on block exit clears it
        with pool.connection() as c2:   # same physical connection (max_size=1)
            row = c2.execute("select current_setting('request.jwt.claim.sub', true) as v").fetchone()
            assert row["v"] in (None, ""), f"claim leaked across checkouts: {row['v']!r}"
    finally:
        pool.close()
