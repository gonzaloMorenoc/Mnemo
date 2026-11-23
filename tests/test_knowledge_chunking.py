"""Troceo del conocimiento largo para el embedder (auditoría 23-nov, #9).

paraphrase-multilingual-MiniLM-L12-v2 trunca a 128 tokens y una sección
importada llega a 4.000 caracteres: sin trocear, la mitad final de un runbook no
existía para la búsqueda. Puro: sin modelo ni BD."""
from src.knowledge.chunking import (
    CHUNK_MAX_CHARS,
    MAX_CHUNKS_PER_ITEM,
    SINGLE_EMBEDDING_MAX_CHARS,
    TITLE_PREFIX_CHARS,
    chunk_texts,
    split_words,
)


def _texto(n_palabras):
    return " ".join(f"palabra{i}" for i in range(n_palabras))


def test_short_item_needs_no_chunks():
    assert chunk_texts("Runbook corto", "reto breve", "enfoque breve") == []


def test_long_item_is_covered_entirely_and_every_chunk_fits():
    body = _texto(600)  # ~6.000 caracteres
    chunks = chunk_texts("Calentar el sandbox del PSP", body, None)
    assert len(chunks) > 1
    assert all(len(c) <= TITLE_PREFIX_CHARS + 1 + CHUNK_MAX_CHARS for c in chunks)
    assert all(c.startswith("Calentar el sandbox del PSP\n") for c in chunks)
    # El final del texto (lo que antes se truncaba) es buscable.
    assert "palabra599" in chunks[-1]
    joined = " ".join(chunks)
    assert all(f"palabra{i} " in joined + " " for i in range(600))


def test_approach_is_also_chunked():
    chunks = chunk_texts("t", _texto(50), "FINAL-DEL-ENFOQUE " + _texto(80))
    assert any("FINAL-DEL-ENFOQUE" in c for c in chunks)


def test_chunks_overlap():
    pieces = split_words(_texto(200), max_chars=100, overlap_chars=30)
    for prev, nxt in zip(pieces, pieces[1:]):
        assert prev.split()[-1] in nxt.split()


def test_a_single_huge_word_is_hard_split():
    pieces = split_words("x" * 1000, max_chars=100, overlap_chars=20)
    assert all(len(p) <= 100 for p in pieces) and "".join(pieces).count("x") >= 1000


def test_chunk_count_is_capped():
    assert len(chunk_texts("t", _texto(20000), None)) == MAX_CHUNKS_PER_ITEM


def test_threshold_is_consistent():
    exact = "a" * (SINGLE_EMBEDDING_MAX_CHARS - 2)
    assert chunk_texts("t", exact, None) == []
