"""Troceo del texto de un item de conocimiento para el embedder. Puro.

Por qué (auditoría 23-nov-2026, #9): el embedder
(paraphrase-multilingual-MiniLM-L12-v2) trunca a 128 tokens, y una sección
importada de Confluence llega a 4.000 caracteres (sectioning.MAX_SECTION_CHARS).
A partir de ~100 palabras el resto del texto no existía para la búsqueda.

Cada item conserva su embedding de siempre (título + reto + enfoque, truncado
por el modelo) y, si el texto no cabe en uno, además un embedding por fragmento
(tabla qa_knowledge_chunks, migración 033). La búsqueda toma, por item, la
distancia del fragmento más cercano.

Medida de los topes: con el tokenizador del modelo, un texto técnico en español
sale a ~3,6 caracteres por token (417 caracteres → 117 tokens). Se presupuesta a
3 caracteres por token, conservador: título (≤ 80) + salto + fragmento (≤ 280)
= 361 caracteres ≈ 120 tokens < 128 (menos los 2 tokens especiales).
"""
from typing import List, Optional


CHUNK_MAX_CHARS = 280
CHUNK_OVERLAP_CHARS = 60
TITLE_PREFIX_CHARS = 80
# Si título + reto + enfoque caben aquí, el embedding del item ya lo cubre entero.
SINGLE_EMBEDDING_MAX_CHARS = TITLE_PREFIX_CHARS + 1 + CHUNK_MAX_CHARS - 1
# Acota el coste de embeber un item (un reto de 4.000 caracteres da ~18).
MAX_CHUNKS_PER_ITEM = 40


def embedding_text(title: str, challenge: Optional[str] = None,
                   approach: Optional[str] = None) -> str:
    """Texto que se embebe para la búsqueda semántica (título + reto + enfoque).
    Vive aquí y se re-exporta desde repository (import histórico)."""
    return "\n".join(p for p in (title, challenge, approach) if p)


def _hard_split(word: str, max_chars: int) -> List[str]:
    return [word[i:i + max_chars] for i in range(0, len(word), max_chars)]


def _overlap_tail(words: List[str], overlap_chars: int) -> List[str]:
    """Las últimas palabras de un fragmento que caben en overlap_chars."""
    tail: List[str] = []
    size = 0
    for w in reversed(words):
        size += len(w) + 1
        if size > overlap_chars:
            break
        tail.insert(0, w)
    return tail


def split_words(text: str, *, max_chars: int = CHUNK_MAX_CHARS,
                overlap_chars: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """Ventanas de palabras de ≤ max_chars con ~overlap_chars de solape. Una
    palabra más larga que la ventana se parte a pelo."""
    words = [p for w in (text or "").split() for p in _hard_split(w, max_chars)]
    pieces: List[str] = []
    current: List[str] = []
    for w in words:
        if current and len(" ".join([*current, w])) > max_chars:
            pieces.append(" ".join(current))
            tail = _overlap_tail(current, overlap_chars)
            current = tail if len(" ".join([*tail, w])) <= max_chars else []
        current = [*current, w]
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_texts(title: str, challenge: Optional[str] = None,
                approach: Optional[str] = None) -> List[str]:
    """Textos a embeber por fragmento, cada uno con el título delante (da
    contexto al fragmento). [] si el item cabe en un solo embedding."""
    if len(embedding_text(title or "", challenge, approach)) <= SINGLE_EMBEDDING_MAX_CHARS:
        return []
    body = "\n".join(p for p in (challenge, approach) if p)
    prefix = (title or "")[:TITLE_PREFIX_CHARS]
    return [f"{prefix}\n{piece}" for piece in split_words(body)][:MAX_CHUNKS_PER_ITEM]
