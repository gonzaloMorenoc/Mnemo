"""Embeddings por fragmento del conocimiento (tabla qa_knowledge_chunks, migración 033).

Ver src/knowledge/chunking.py para el porqué (auditoría 23-nov, #9). Funciones
sobre un cursor abierto: no hacen commit ni comprueban membership (lo hace el
llamador, igual que insert_qa_knowledge).

Tolerante a que la migración 033 aún no esté aplicada: sin la tabla, no se
escriben fragmentos y la búsqueda usa solo qa_knowledge.embedding (como antes).
"""
from typing import Any, List, Optional, Sequence

from pgvector import Vector

from src.knowledge.chunking import chunk_texts

_TABLE_EXISTS_SQL = "select to_regclass('public.qa_knowledge_chunks') is not null as ok"

_COLUMNS = "k.id, k.kind, k.title, k.challenge, k.approach, k.outcome, k.domain, k.confidence"

# Con proyecto: lo de ese proyecto + lo de toda la organización (project null). Sin
# proyecto (%(proj)s null): todo, como antes.
_PROJECT = "(%(proj)s::text is null or k.project is null or k.project = %(proj)s)"

# Solo el embedding del item (sin la migración 033).
_SEARCH_ITEMS_ONLY = f"""
    select {_COLUMNS}, k.embedding <=> %(q)s as dist
    from public.qa_knowledge k
    where k.org_id = %(org)s and k.status = 'activo' and k.embedding is not null
      and {_PROJECT}
      and k.embedding <=> %(q)s < %(max_dist)s
    order by dist limit %(k)s
"""

# Por item, la distancia mínima entre su embedding y los de sus fragmentos.
_SEARCH_WITH_CHUNKS = f"""
    with cand as (
        select k.id as knowledge_id, k.embedding <=> %(q)s as dist
        from public.qa_knowledge k
        where k.org_id = %(org)s and k.status = 'activo' and k.embedding is not null
          and {_PROJECT}
        union all
        select c.knowledge_id, c.embedding <=> %(q)s as dist
        from public.qa_knowledge_chunks c
        join public.qa_knowledge k on k.id = c.knowledge_id
        where c.org_id = %(org)s and k.org_id = %(org)s and k.status = 'activo'
          and {_PROJECT}
    ), best as (
        select knowledge_id, min(dist) as dist from cand group by knowledge_id
    )
    select {_COLUMNS}, b.dist as dist
    from best b join public.qa_knowledge k on k.id = b.knowledge_id
    where b.dist < %(max_dist)s
    order by b.dist limit %(k)s
"""


def chunks_table_exists(cur) -> bool:
    """¿Está aplicada la migración 033? Consulta de catálogo, barata."""
    cur.execute(_TABLE_EXISTS_SQL)
    row = cur.fetchone()
    return bool(row.get("ok")) if isinstance(row, dict) else False


def chunk_embeddings(embedder, title: str, challenge: Optional[str],
                     approach: Optional[str]) -> List[Vector]:
    """Un embedding por fragmento; [] si el item cabe en su embedding único.
    Se llama FUERA de la transacción (no retenerla mientras calcula el modelo)."""
    return [Vector(list(embedder.embed(t))) for t in chunk_texts(title, challenge, approach)]


def replace_chunks(cur, *, knowledge_id: Any, org_id: str,
                   embeddings: Sequence[Any]) -> int:
    """Sustituye los fragmentos del item. Devuelve cuántos quedan guardados."""
    if not chunks_table_exists(cur):
        return 0
    cur.execute("delete from public.qa_knowledge_chunks where knowledge_id = %s",
                (knowledge_id,))
    if embeddings:
        cur.executemany(
            "insert into public.qa_knowledge_chunks (knowledge_id, org_id, chunk_index, embedding)"
            " values (%s, %s, %s, %s)",
            [(knowledge_id, org_id, i, e) for i, e in enumerate(embeddings)])
    return len(embeddings)


def search_sql(*, with_chunks: bool) -> str:
    return _SEARCH_WITH_CHUNKS if with_chunks else _SEARCH_ITEMS_ONLY
