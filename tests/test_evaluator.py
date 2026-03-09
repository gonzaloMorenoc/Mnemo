"""
Unit tests for src/evaluator.py

The evaluator uses a heuristic token-overlap approach.
These tests validate correctness and edge-case handling without requiring Ollama.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.evaluator import RAGASEvaluator


@pytest.fixture
def evaluator():
    """Evaluator instance with the LLM dependency mocked out."""
    with patch("src.evaluator.OllamaLLM"):
        return RAGASEvaluator()


class TestReturnShape:
    def test_returns_dict(self, evaluator):
        result = evaluator.evaluate_response("error", "fix", ["context"])
        assert isinstance(result, dict)

    def test_has_faithfulness_key(self, evaluator):
        result = evaluator.evaluate_response("error", "fix", ["context"])
        assert "faithfulness" in result

    def test_has_relevancy_key(self, evaluator):
        result = evaluator.evaluate_response("error", "fix", ["context"])
        assert "relevancy" in result


class TestScoreRange:
    def test_faithfulness_between_0_and_1(self, evaluator):
        result = evaluator.evaluate_response(
            "selenium timeout", "add no-sandbox chrome flag", ["chrome timeout fix"]
        )
        assert 0.0 <= result["faithfulness"] <= 1.0

    def test_relevancy_between_0_and_1(self, evaluator):
        result = evaluator.evaluate_response(
            "selenium timeout", "add no-sandbox chrome flag", ["chrome timeout fix"]
        )
        assert 0.0 <= result["relevancy"] <= 1.0


class TestFaithfulnessHeuristic:
    def test_high_faithfulness_when_answer_copies_context_tokens(self, evaluator):
        context = ["stale element reference re-fetch the element dom mutation fix"]
        answer = "stale element reference fix: re-fetch element after dom mutation"
        result = evaluator.evaluate_response("stale element", answer, context)
        assert result["faithfulness"] > 0.4

    def test_zero_faithfulness_on_empty_answer(self, evaluator):
        result = evaluator.evaluate_response("some error", "", ["context doc"])
        assert result["faithfulness"] == 0.0

    def test_zero_faithfulness_on_empty_context(self, evaluator):
        result = evaluator.evaluate_response("some error", "some fix", [])
        assert result["faithfulness"] == 0.0

    def test_lower_faithfulness_when_answer_diverges_from_context(self, evaluator):
        context = ["completely unrelated document about cooking pasta recipes"]
        answer = "selenium timeout fix: set page_load_timeout to 30 seconds"
        result = evaluator.evaluate_response("selenium timeout", answer, context)
        # Answer tokens won't appear in a cooking context → low faithfulness
        assert result["faithfulness"] < 0.5


class TestRelevancyHeuristic:
    def test_high_relevancy_when_answer_addresses_question_terms(self, evaluator):
        question = "selenium timeout webdriver"
        answer = "selenium timeout fix: increase webdriver wait time"
        result = evaluator.evaluate_response(question, answer, ["context"])
        assert result["relevancy"] > 0.4

    def test_zero_relevancy_on_empty_question(self, evaluator):
        result = evaluator.evaluate_response("", "some fix", ["context"])
        assert result["relevancy"] == 0.0

    def test_zero_relevancy_on_empty_answer(self, evaluator):
        result = evaluator.evaluate_response("error type", "", ["context"])
        assert result["relevancy"] == 0.0


class TestEdgeCases:
    def test_multiple_context_docs_are_combined(self, evaluator):
        context = ["selenium timeout", "chrome driver fix no-sandbox"]
        answer = "selenium chrome timeout fix no-sandbox"
        result = evaluator.evaluate_response("selenium", answer, context)
        # With combined context, more answer tokens should match
        assert result["faithfulness"] > 0.0

    def test_scores_are_rounded_to_two_decimals(self, evaluator):
        result = evaluator.evaluate_response("err", "fix this err", ["fix this err now"])
        assert result["faithfulness"] == round(result["faithfulness"], 2)
        assert result["relevancy"] == round(result["relevancy"], 2)
