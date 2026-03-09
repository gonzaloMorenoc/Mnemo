"""
Golden dataset coverage tests.

These tests verify that the 5 canonical QA errors (qa_test_errors.json) are
correctly loaded, chunked, and indexed by the data pipeline.
They act as a regression guard: if loading or chunking logic breaks, the
retrieval quality of the whole system silently degrades.

No Ollama or ChromaDB required — only the loader is exercised.
"""
import pytest
from langchain_core.documents import Document
from src.loader import LogLoader


KEY_ERROR_TERMS = [
    "TimeoutException",
    "StaleElementReferenceException",
    "AssertionError",
    "ConnectionRefusedError",
    "NoSuchElementException",
]

KEY_SOLUTION_TERMS = [
    "pageLoadTimeout",          # Fix for TimeoutException
    "reintento",                # Fix for StaleElementReference
    "credenciales",             # Fix for AssertionError (expired credentials)
    "docker-compose",           # Fix for ConnectionRefused
    "WebDriverWait",            # Fix for NoSuchElement
]


class TestGoldenDatasetLoading:
    """All 5 golden dataset entries must be fully loaded and chunked."""

    def test_at_least_five_chunks_produced(self, data_dir_with_golden, golden_dataset):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        assert len(chunks) >= len(golden_dataset), (
            f"Expected ≥{len(golden_dataset)} chunks (one per entry), got {len(chunks)}"
        )

    def test_all_chunks_are_valid_documents(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        for chunk in chunks:
            assert isinstance(chunk, Document)
            assert chunk.page_content.strip(), "Chunk has empty content"

    def test_all_five_error_types_are_indexed(self, data_dir_with_golden):
        """Each exception class name must appear in at least one chunk."""
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        all_content = " ".join(c.page_content for c in chunks)

        missing = [term for term in KEY_ERROR_TERMS if term not in all_content]
        assert not missing, f"These error terms are missing from the index: {missing}"

    def test_all_five_solutions_are_indexed(self, data_dir_with_golden):
        """Key solution terms from previous_fix fields must be indexed."""
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        all_content = " ".join(c.page_content for c in chunks)

        missing = [term for term in KEY_SOLUTION_TERMS if term not in all_content]
        assert not missing, f"These solution terms are missing from the index: {missing}"

    def test_chunks_have_json_type_metadata(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        json_chunks = [c for c in chunks if c.metadata.get("type") == "json"]
        assert json_chunks, "No chunks have type='json' metadata"

    def test_all_chunks_have_zero_initial_rating(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        json_chunks = [c for c in chunks if c.metadata.get("type") == "json"]
        assert all(c.metadata["rating"] == 0 for c in json_chunks)

    def test_each_entry_has_source_metadata(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        json_chunks = [c for c in chunks if c.metadata.get("type") == "json"]
        for chunk in json_chunks:
            assert "source" in chunk.metadata
            assert chunk.metadata["source"]  # not empty


class TestGoldenDatasetBM25Readiness:
    """Chunks must contain the exact tokens BM25 needs to match each error type."""

    @pytest.mark.parametrize("error_term", KEY_ERROR_TERMS)
    def test_bm25_token_present(self, data_dir_with_golden, error_term):
        """Each critical exception class name must be preserved verbatim in at least one chunk."""
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        found = any(error_term in chunk.page_content for chunk in chunks)
        assert found, (
            f"BM25 keyword '{error_term}' not found in any chunk. "
            "Exact-match retrieval for this error type will fail."
        )

    def test_selenium_error_codes_preserved(self, data_dir_with_golden):
        """Selector strings like '#submit-btn' that BM25 must match exactly."""
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        all_content = " ".join(c.page_content for c in chunks)
        assert "#submit-btn" in all_content or "submit-btn" in all_content


class TestStructuredOutputFormat:
    """Documents must follow the expected Error/Stack Trace/Solution structure."""

    def test_error_prefix_present(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        all_content = " ".join(c.page_content for c in chunks)
        assert "Error:" in all_content

    def test_stack_trace_prefix_present(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        all_content = " ".join(c.page_content for c in chunks)
        assert "Stack Trace:" in all_content

    def test_solution_prefix_present(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        all_content = " ".join(c.page_content for c in chunks)
        assert "Solution:" in all_content
