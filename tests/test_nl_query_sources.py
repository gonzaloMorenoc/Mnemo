"""Tests for answer_over_sources and the refactored answer_question."""
from unittest.mock import patch

from src.ai.nl_query import answer_over_sources, answer_question

_SOURCES = [
    {"id": "s1", "content": "checkout falla con 500", "type": "defect"},
    {"id": "s2", "content": "login timeout frecuente", "type": "knowledge"},
]

_FAMS = [
    {"family_id": "fam1", "title": "checkout 500", "label": "real",
     "occurrence_count": 3, "root_cause": "backend 500"},
    {"family_id": "fam2", "title": "login timeout", "label": "flaky",
     "occurrence_count": 1, "root_cause": None},
]


def test_answer_over_sources_with_llm():
    """generate_structured returns a dict → answer and citations are used."""
    with patch("src.ai.nl_query.generate_structured", return_value={"answer": "Checkout falla.", "citations": ["s1"]}):
        res = answer_over_sources(question="¿qué rompe checkout?", sources=_SOURCES)
    assert res["answer"] == "Checkout falla."
    assert res["citations"] == ["s1"]


def test_answer_over_sources_llm_none_returns_fallback():
    """generate_structured returns None → fallback with citations from top sources."""
    with patch("src.ai.nl_query.generate_structured", return_value=None):
        res = answer_over_sources(question="¿qué rompe checkout?", sources=_SOURCES)
    assert "Fuentes relevantes" in res["answer"]
    assert res["citations"] == ["s1", "s2"]


def test_answer_over_sources_empty_sources():
    """No sources → fixed 'no info' message with empty citations."""
    res = answer_over_sources(question="¿algo?", sources=[])
    assert "No hay información" in res["answer"]
    assert res["citations"] == []


def test_answer_question_delegates_to_answer_over_sources():
    """answer_question builds sources from families and delegates."""
    with patch("src.ai.nl_query.generate_structured",
               return_value={"answer": "Checkout falla.", "citations": ["fam1"]}) as mock_gen:
        res = answer_question(question="¿qué rompe checkout?", families=_FAMS)
    assert res["answer"] == "Checkout falla."
    assert res["citations"] == ["fam1"]
    # generate_structured was called (i.e., not short-circuited)
    assert mock_gen.called


def test_answer_question_no_families():
    """answer_question with empty families returns 'no info' branch via answer_over_sources."""
    res = answer_question(question="¿algo?", families=[])
    assert res["citations"] == []
    assert res["answer"]  # non-empty message


def test_answer_question_degrades_without_llm():
    """answer_question fallback includes family titles in citations."""
    with patch("src.ai.nl_query.generate_structured", return_value=None):
        res = answer_question(question="¿qué rompe checkout?", families=_FAMS)
    assert res["citations"] == ["fam1", "fam2"]
    assert res["answer"]
