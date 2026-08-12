"""Tests for KnowledgeService.search_unified and .ask."""
from unittest.mock import MagicMock, patch

from src.knowledge.service import KnowledgeService


def _make_service():
    """Build a KnowledgeService with fake repos and a fake embedder."""
    fake_knowledge_repo = MagicMock()
    fake_knowledge_repo.search_semantic.return_value = [
        {"id": "k1", "title": "Lesson: checkout errors", "challenge": "high error rate",
         "approach": "circuit breaker", "outcome": "reduced errors", "confidence": "confirmado"},
    ]

    fake_assurance_repo = MagicMock()
    # El contrato REAL de AssuranceRepository.search_families_semantic devuelve la
    # familia bajo la clave "family_id" (no "id"). El mock debe reflejarlo o el test
    # valida una ficción — que fue justo lo que dejó pasar el KeyError en producción.
    fake_assurance_repo.search_families_semantic.return_value = [
        {"family_id": "f1", "title": "checkout 500", "label": "real",
         "root_cause": "backend 500", "signature": "sig", "occurrence_count": 3},
    ]

    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [0.1] * 384

    return KnowledgeService(fake_knowledge_repo, fake_assurance_repo, embedder=fake_embedder)


def test_search_unified_merges_knowledge_and_defect():
    """search_unified returns items of type 'knowledge' AND type 'defect'."""
    svc = _make_service()
    results = svc.search_unified(user_id="u1", org_id="o1", query="checkout errors")

    types = {r["type"] for r in results}
    assert "knowledge" in types
    assert "defect" in types
    assert len(results) == 2


def test_search_unified_knowledge_item_fields():
    """Knowledge items have id, type, title, content."""
    svc = _make_service()
    results = svc.search_unified(user_id="u1", org_id="o1", query="checkout")
    knowledge_items = [r for r in results if r["type"] == "knowledge"]
    assert len(knowledge_items) == 1
    item = knowledge_items[0]
    assert item["id"] == "k1"
    assert "checkout errors" in item["content"]


def test_search_unified_defect_item_fields():
    """Defect items have id, type, title, content with 'defecto=' prefix."""
    svc = _make_service()
    results = svc.search_unified(user_id="u1", org_id="o1", query="checkout")
    defect_items = [r for r in results if r["type"] == "defect"]
    assert len(defect_items) == 1
    item = defect_items[0]
    assert item["id"] == "f1"
    assert "defecto=" in item["content"]


def test_ask_calls_answer_over_sources_and_returns_result():
    """ask calls answer_over_sources with the merged sources and returns its result."""
    svc = _make_service()
    fake_answer = {"answer": "Checkout falla por backend.", "citations": ["f1"]}
    with patch("src.ai.nl_query.answer_over_sources", return_value=fake_answer) as mock_aos:
        result = svc.ask(user_id="u1", org_id="o1", question="¿qué rompe checkout?")

    assert result == fake_answer
    mock_aos.assert_called_once()
    call_kwargs = mock_aos.call_args.kwargs
    assert call_kwargs["question"] == "¿qué rompe checkout?"
    assert isinstance(call_kwargs["sources"], list)
    assert len(call_kwargs["sources"]) == 2


def test_ask_uses_embedder_for_query():
    """ask embeds the question query before searching repos."""
    svc = _make_service()
    with patch("src.ai.nl_query.answer_over_sources", return_value={"answer": "ok", "citations": []}):
        svc.ask(user_id="u1", org_id="o1", question="mi pregunta")

    svc.embedder.embed.assert_called_once_with("mi pregunta")


def test_search_unified_defect_content_includes_label_reason():
    """La razón de la etiqueta (conocimiento tácito del senior) entra en el content
    buscable del defecto. Auditoría 2026-08-12, H1."""
    svc = _make_service()
    svc.assurance.search_families_semantic.return_value = [
        {"family_id": "f1", "title": "checkout timeout", "label": "flaky",
         "root_cause": None, "signature": "sig", "occurrence_count": 3,
         "label_reason": "Timeouts por runners fríos del sandbox del PSP"},
    ]
    results = svc.search_unified(user_id="u1", org_id="o1", query="checkout inestable")
    defect = next(r for r in results if r["type"] == "defect")
    assert "runners fríos" in defect["content"]
