"""Mezcla por relevancia del contexto del LLM (auditoría 23-nov, #8).

Antes: 8 items de conocimiento primero y 8 familias después, y el LLM recibía
solo los 10 primeros → con ≥8 items de conocimiento llegaban 2 familias, justo
las que llevan la razón del senior. Ahora: orden por distancia y un mínimo de
huecos reservado para familias con razón o lección dentro del corte.
"""
from unittest.mock import MagicMock

from src.ai.generate import MAX_CONTEXT_SOURCES, _build_context_block
from src.knowledge.ranking import MIN_FAMILY_SLOTS, merge_by_relevance
from src.knowledge.service import KnowledgeService


def _k(i, dist):
    return {"id": f"k{i}", "type": "knowledge", "dist": dist}


def _f(i, dist, priority=True):
    return {"id": f"f{i}", "type": "defect", "dist": dist, "priority": priority}


def test_orders_by_distance_across_types():
    out = merge_by_relevance([_k(1, 0.5), _k(2, 0.1)], [_f(1, 0.3)])
    assert [s["id"] for s in out] == ["k2", "f1", "k1"]


def test_reserves_family_slots_inside_the_cut():
    knowledge = [_k(i, 0.01 * i) for i in range(1, 9)]          # 8 muy relevantes
    families = [_f(i, 0.5 + 0.01 * i) for i in range(1, 9)]     # 8 con razón, menos cerca
    out = merge_by_relevance(knowledge, families, limit=10)
    top = out[:10]
    assert sum(1 for s in top if s["type"] == "defect") >= MIN_FAMILY_SLOTS
    assert len(out) == 16                                      # nada se pierde: el resto va detrás


def test_families_without_reason_or_lesson_get_no_reserved_slot():
    knowledge = [_k(i, 0.01 * i) for i in range(1, 11)]
    families = [_f(1, 0.9, priority=False)]
    top = merge_by_relevance(knowledge, families, limit=10)[:10]
    assert all(s["type"] == "knowledge" for s in top)


def test_missing_distance_sorts_last_but_keeps_order():
    out = merge_by_relevance([{"id": "a", "type": "knowledge"}], [_f(1, 0.2, priority=False)])
    assert [s["id"] for s in out] == ["f1", "a"]


def test_context_block_cut_is_a_constant():
    ctx = [{"id": str(i), "content": "x"} for i in range(MAX_CONTEXT_SOURCES + 5)]
    assert _build_context_block(ctx).count("[") == MAX_CONTEXT_SOURCES


def test_search_unified_brings_reasoned_families_into_the_llm_cut():
    krepo, arepo, emb = MagicMock(), MagicMock(), MagicMock()
    emb.embed.return_value = [0.1] * 384
    krepo.search_semantic.return_value = [
        {"id": f"k{i}", "title": f"t{i}", "dist": 0.01 * i} for i in range(1, 9)]
    arepo.search_families_semantic.return_value = [
        {"family_id": f"f{i}", "title": "TimeoutError", "label": "infra",
         "label_reason": "sandbox del PSP en frío", "has_lesson": False,
         "dist": 0.5 + 0.01 * i} for i in range(1, 9)]
    out = KnowledgeService(krepo, arepo, embedder=emb).search_unified(
        user_id="u", org_id="o", query="q")
    top = out[:MAX_CONTEXT_SOURCES]
    assert sum(1 for s in top if s["type"] == "defect") >= MIN_FAMILY_SLOTS
