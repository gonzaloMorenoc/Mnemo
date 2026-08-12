"""El script de re-embebido tiene que poder ESCRIBIR vectores.

Regresión de un fallo real (12-ago-2026): `python3 -m scripts.reembed` moría en
el primer UPDATE con `psycopg.ProgrammingError: cannot adapt type 'Vector'`.

La causa: todas las escrituras de vectores del código de producción van por
`get_pool()`, cuyo `configure` llama a `register_vector(conn)` (src/db/pool.py).
El script conecta con `psycopg.connect()` directo — necesario para el bypass de
RLS, mismo patrón que reseed_demo.py — pero esos otros scripts NO escriben
vectores, así que el patrón copiado no traía el adaptador de pgvector.

El `--dry-run` no cazó nada porque no escribe: nunca ejercitaba la adaptación.

Marcado integration: necesita BD real (el CI lo excluye).
"""
import pytest
from pgvector import Vector

from scripts.reembed import _connect

pytestmark = pytest.mark.integration


def test_connect_adapta_vectores():
    """La conexión del script sabe pasar un Vector como parámetro.

    No escribe: el cast en un SELECT ejercita exactamente la adaptación que
    fallaba, sin tocar ninguna fila.
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select %s::vector as v", (Vector([0.1] * 384),))
        assert cur.fetchone()["v"] is not None
