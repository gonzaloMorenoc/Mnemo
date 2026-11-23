"""Rellena los fragmentos (migración 033) del conocimiento que aún no los tiene.

Sustituye al paso manual `reembed --only-knowledge` tras desplegar: el backend lo hace
solo al arrancar, en segundo plano y sin bloquear peticiones. Es idempotente: un item con
fragmentos ya guardados no se toca, y uno corto (cabe en su embedding) no genera nada.
Best-effort: un fallo se registra y se reintenta en el siguiente arranque.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

from psycopg.rows import dict_row

from src.knowledge.chunk_store import chunk_embeddings, chunks_table_exists, replace_chunks
from src.knowledge.chunking import chunk_texts

logger = logging.getLogger(__name__)

ENV_SWITCH = "MNEMO_CHUNK_BACKFILL_ON_START"   # "false" lo desactiva
MAX_ITEMS_PER_RUN = 2000                       # cota por arranque; el resto, en el siguiente

_CANDIDATES_SQL = """
    select k.id, k.org_id, k.title, k.challenge, k.approach
    from public.qa_knowledge k
    where k.embedding is not null
      and not exists (select 1 from public.qa_knowledge_chunks c where c.knowledge_id = k.id)
    order by k.created_at
    limit %s
"""


def backfill_missing_chunks(connection_factory: Callable, embedder,
                            limit: int = MAX_ITEMS_PER_RUN) -> int:
    """Calcula y guarda los fragmentos que faltan. Devuelve cuántos items rellenó."""
    with connection_factory() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if not chunks_table_exists(cur):
                return 0
            cur.execute(_CANDIDATES_SQL, (limit,))
            candidates = cur.fetchall()
        conn.commit()
        filled = 0
        for item in candidates:
            if not chunk_texts(item["title"], item["challenge"], item["approach"]):
                continue   # cabe en su embedding único: no hay fragmentos que guardar
            # El modelo, FUERA de la transacción.
            embeddings = chunk_embeddings(embedder, item["title"], item["challenge"],
                                          item["approach"])
            with conn.cursor(row_factory=dict_row) as cur:
                replace_chunks(cur, knowledge_id=item["id"], org_id=str(item["org_id"]),
                               embeddings=embeddings)
            conn.commit()
            filled += 1
    return filled


def _enabled() -> bool:
    return os.getenv(ENV_SWITCH, "true").strip().lower() not in ("false", "0", "no")


def start_backfill_in_background(connection_factory: Callable,
                                 embedder_factory: Callable) -> Optional[threading.Thread]:
    """Lanza el relleno en un hilo daemon (no retrasa el arranque ni el health)."""
    if not _enabled():
        logger.info("relleno de fragmentos desactivado (%s=false)", ENV_SWITCH)
        return None

    def _run() -> None:
        try:
            filled = backfill_missing_chunks(connection_factory, embedder_factory())
            logger.info("relleno de fragmentos: %d items", filled)
        except Exception:  # noqa: BLE001 — best-effort: se reintenta en el próximo arranque
            logger.exception("relleno de fragmentos falló")

    thread = threading.Thread(target=_run, name="chunk-backfill", daemon=True)
    thread.start()
    return thread
