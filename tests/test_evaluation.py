"""
Tests for the RAGAS evaluation pipeline.

These tests validate:
1. Evaluator initialization and metric configuration
2. Single-response evaluation output format and ranges
3. Batch dataset evaluation
4. Metric quality thresholds (smoke tests)
5. Edge cases and error handling

Usage:
    # Run all evaluation tests
    pytest tests/test_evaluation.py -v

    # Run only unit tests (no LLM required)
    pytest tests/test_evaluation.py -v -m "not integration"

    # Run integration tests (requires Ollama running)
    pytest tests/test_evaluation.py -v -m integration
"""
import pytest
import json
import os
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Unit tests (no LLM / Ollama required)
# ---------------------------------------------------------------------------


class TestEvalDataset:
    """Validates the evaluation dataset structure and content."""

    def test_dataset_exists(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "eval_dataset.json"
        )
        assert os.path.exists(path), "eval_dataset.json not found"

    def test_dataset_has_minimum_samples(self, eval_dataset):
        assert len(eval_dataset) >= 5, "Dataset should have at least 5 test cases"

    def test_dataset_sample_structure(self, eval_dataset):
        required_keys = {"question", "ground_truth", "contexts"}
        for i, sample in enumerate(eval_dataset):
            missing = required_keys - set(sample.keys())
            assert not missing, f"Sample {i} missing keys: {missing}"

    def test_dataset_contexts_are_lists(self, eval_dataset):
        for i, sample in enumerate(eval_dataset):
            assert isinstance(sample["contexts"], list), f"Sample {i}: contexts must be a list"
            assert len(sample["contexts"]) > 0, f"Sample {i}: contexts must not be empty"

    def test_dataset_no_empty_fields(self, eval_dataset):
        for i, sample in enumerate(eval_dataset):
            assert sample["question"].strip(), f"Sample {i}: question is empty"
            assert sample["ground_truth"].strip(), f"Sample {i}: ground_truth is empty"


class TestEvaluatorInit:
    """Tests evaluator construction without needing a running LLM."""

    def test_evaluator_imports(self):
        from src.evaluator import RAGASEvaluator
        assert RAGASEvaluator is not None

    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_evaluator_creates_4_metrics(self, mock_emb, mock_llm):
        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()
        assert len(evaluator.metrics) == 4

    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_evaluator_metric_types(self, mock_emb, mock_llm):
        from src.evaluator import RAGASEvaluator
        from ragas.metrics import Faithfulness, ResponseRelevancy

        evaluator = RAGASEvaluator()
        metric_types = [type(m).__name__ for m in evaluator.metrics]
        assert "Faithfulness" in metric_types
        assert "ResponseRelevancy" in metric_types


class TestEvaluatorOutputFormat:
    """Tests that evaluate_response returns correct dict format even on error."""

    @patch("src.evaluator.evaluate")
    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_returns_dict_with_4_metrics(self, mock_emb, mock_llm, mock_eval):
        import pandas as pd
        mock_eval.return_value.to_pandas.return_value = pd.DataFrame([{
            "faithfulness": 0.85,
            "response_relevancy": 0.90,
            "llm_context_precision_without_reference": 0.88,
            "llm_context_recall": 0.82,
        }])

        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()
        result = evaluator.evaluate_response(
            question="Test error",
            answer="Test answer",
            contexts=["context1"],
        )

        assert isinstance(result, dict)
        expected_keys = {"faithfulness", "relevancy", "context_precision", "context_recall"}
        assert set(result.keys()) == expected_keys

    @patch("src.evaluator.evaluate")
    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_metrics_in_valid_range(self, mock_emb, mock_llm, mock_eval):
        import pandas as pd
        mock_eval.return_value.to_pandas.return_value = pd.DataFrame([{
            "faithfulness": 0.85,
            "response_relevancy": 0.90,
            "llm_context_precision_without_reference": 0.88,
            "llm_context_recall": 0.82,
        }])

        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()
        result = evaluator.evaluate_response("q", "a", ["c"])

        for key, value in result.items():
            assert 0.0 <= value <= 1.0, f"{key}={value} out of range [0, 1]"

    @patch("src.evaluator.evaluate", side_effect=Exception("LLM unavailable"))
    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_graceful_failure_returns_zeros(self, mock_emb, mock_llm, mock_eval):
        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()
        result = evaluator.evaluate_response("q", "a", ["c"])

        assert result is not None
        assert all(v == 0.0 for v in result.values())

    @patch("src.evaluator.evaluate")
    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_with_reference(self, mock_emb, mock_llm, mock_eval):
        import pandas as pd
        mock_eval.return_value.to_pandas.return_value = pd.DataFrame([{
            "faithfulness": 0.9,
            "response_relevancy": 0.92,
            "llm_context_precision_without_reference": 0.85,
            "llm_context_recall": 0.88,
        }])

        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()
        result = evaluator.evaluate_response(
            "error", "answer", ["ctx"], reference="ground truth"
        )
        assert result["faithfulness"] == 0.9


class TestBatchEvaluation:
    """Tests for evaluate_dataset method."""

    @patch("src.evaluator.evaluate")
    @patch("src.evaluator.OllamaLLM")
    @patch("src.evaluator.OllamaEmbeddings")
    def test_batch_returns_expected_structure(self, mock_emb, mock_llm, mock_eval):
        import pandas as pd
        mock_eval.return_value.to_pandas.return_value = pd.DataFrame([
            {"faithfulness": 0.8, "response_relevancy": 0.85,
             "llm_context_precision_without_reference": 0.82, "llm_context_recall": 0.78},
            {"faithfulness": 0.9, "response_relevancy": 0.88,
             "llm_context_precision_without_reference": 0.91, "llm_context_recall": 0.85},
        ])

        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()

        # Use only 2 samples from the real dataset
        dataset_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "eval_dataset.json"
        )
        result = evaluator.evaluate_dataset(dataset_path)

        assert "per_sample" in result
        assert "averages" in result
        assert "total_samples" in result
        assert result["total_samples"] >= 5


# ---------------------------------------------------------------------------
# Integration tests (require Ollama with the configured model running)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRAGASIntegration:
    """
    End-to-end tests that run actual RAGAS evaluation with Ollama.
    Requires: Ollama running with the configured model.
    Run with: pytest tests/test_evaluation.py -v -m integration
    """

    @pytest.fixture(autouse=True)
    def check_ollama(self):
        """Skip integration tests if Ollama is not available."""
        import subprocess
        try:
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/tags"],
                capture_output=True, timeout=5
            )
            if result.returncode != 0:
                pytest.skip("Ollama not available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Ollama not available")

    def test_single_evaluation_real(self, single_sample):
        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()
        result = evaluator.evaluate_response(
            question=single_sample["question"],
            answer=single_sample["ground_truth"],
            contexts=single_sample["contexts"],
            reference=single_sample["ground_truth"],
        )

        assert isinstance(result, dict)
        assert len(result) == 4
        for key, value in result.items():
            assert 0.0 <= value <= 1.0, f"{key}={value} out of range"

    def test_faithfulness_high_for_grounded_answer(self, single_sample):
        """An answer that comes directly from context should have high faithfulness."""
        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()

        # Use context content as the answer (perfectly grounded)
        grounded_answer = single_sample["contexts"][0]
        result = evaluator.evaluate_response(
            question=single_sample["question"],
            answer=grounded_answer,
            contexts=single_sample["contexts"],
        )
        assert result["faithfulness"] >= 0.5, (
            f"Faithfulness should be high for grounded answer, got {result['faithfulness']}"
        )

    def test_relevancy_low_for_irrelevant_answer(self, single_sample):
        """A completely irrelevant answer should score lower on relevancy."""
        from src.evaluator import RAGASEvaluator
        evaluator = RAGASEvaluator()

        result = evaluator.evaluate_response(
            question=single_sample["question"],
            answer="La receta de paella lleva arroz, azafrán y mariscos.",
            contexts=single_sample["contexts"],
        )
        # Irrelevant answer should have lower relevancy
        assert result["relevancy"] < 0.7, (
            f"Relevancy should be low for irrelevant answer, got {result['relevancy']}"
        )
