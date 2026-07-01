from typing import Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from src.config import DATABASE_URL

_pool: Optional[ConnectionPool] = None


def _configure(conn) -> None:
    conn.row_factory = dict_row
    register_vector(conn)


def get_pool() -> ConnectionPool:
    """Pool global lazy. Pre-abre min_size conexiones (el connect lento se paga aquí)."""
    global _pool
    if _pool is None:
        pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=2,
            max_size=10,
            open=False,
            timeout=10,
            configure=_configure,
            kwargs={"row_factory": dict_row},
        )
        pool.open(wait=True, timeout=15)
        _pool = pool
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
