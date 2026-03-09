"""
Unit tests for src/loader.py

These tests do NOT require Ollama, ChromaDB, or any external service.
They cover the data ingestion and chunking logic in isolation.
"""
import json
import pytest
from langchain_core.documents import Document
from src.loader import LogLoader


# ─────────────────────────────────────────────────────────────
# _process_json_entry
# ─────────────────────────────────────────────────────────────

class TestProcessJsonEntry:
    """_process_json_entry converts a single dict into a LangChain Document."""

    def _make_loader(self):
        # Instantiate without hitting __init__ to avoid touching the filesystem
        loader = object.__new__(LogLoader)
        return loader

    def test_all_known_fields_appear_in_content(self):
        loader = self._make_loader()
        entry = {
            "error_message": "TimeoutException",
            "stack_trace": "at line 89 in base.py",
            "previous_fix": "Add --no-sandbox to Chrome options",
        }
        doc = loader._process_json_entry(entry, "test.json")
        assert "Error: TimeoutException" in doc.page_content
        assert "Stack Trace: at line 89 in base.py" in doc.page_content
        assert "Solution: Add --no-sandbox to Chrome options" in doc.page_content

    def test_only_error_message(self):
        loader = self._make_loader()
        doc = loader._process_json_entry({"error_message": "NullPointerException"}, "f.json")
        assert "Error: NullPointerException" in doc.page_content
        assert "Stack Trace" not in doc.page_content
        assert "Solution" not in doc.page_content

    def test_unknown_fields_fall_back_to_json_dump(self):
        loader = self._make_loader()
        entry = {"custom_key": "custom_value", "count": 42}
        doc = loader._process_json_entry(entry, "f.json")
        assert "custom_key" in doc.page_content
        assert "custom_value" in doc.page_content

    def test_metadata_type_is_json(self):
        loader = self._make_loader()
        doc = loader._process_json_entry({"error_message": "Err"}, "src.json")
        assert doc.metadata["type"] == "json"

    def test_metadata_source_matches_argument(self):
        loader = self._make_loader()
        doc = loader._process_json_entry({"error_message": "Err"}, "/data/logs/errors.json")
        assert doc.metadata["source"] == "/data/logs/errors.json"

    def test_metadata_initial_rating_is_zero(self):
        loader = self._make_loader()
        doc = loader._process_json_entry({"error_message": "Err"}, "f.json")
        assert doc.metadata["rating"] == 0

    def test_returns_document_instance(self):
        loader = self._make_loader()
        doc = loader._process_json_entry({"error_message": "Err"}, "f.json")
        assert isinstance(doc, Document)


# ─────────────────────────────────────────────────────────────
# _process_json_file
# ─────────────────────────────────────────────────────────────

class TestProcessJsonFile:
    """_process_json_file handles both JSON arrays and single JSON objects."""

    def _make_loader(self):
        return object.__new__(LogLoader)

    def test_array_returns_one_doc_per_entry(self, tmp_json_array_file, golden_dataset):
        loader = self._make_loader()
        docs = loader._process_json_file(tmp_json_array_file)
        assert docs is not None
        assert len(docs) == len(golden_dataset)

    def test_all_array_docs_are_document_instances(self, tmp_json_array_file):
        loader = self._make_loader()
        docs = loader._process_json_file(tmp_json_array_file)
        assert all(isinstance(d, Document) for d in docs)

    def test_single_object_returns_list_of_one(self, tmp_json_single_file):
        loader = self._make_loader()
        docs = loader._process_json_file(tmp_json_single_file)
        assert docs is not None
        assert len(docs) == 1
        assert isinstance(docs[0], Document)

    def test_invalid_json_returns_none(self, tmp_path):
        loader = self._make_loader()
        bad = tmp_path / "bad.json"
        bad.write_text("{{not valid json!!", encoding="utf-8")
        assert loader._process_json_file(str(bad)) is None

    def test_nonexistent_path_returns_none(self):
        loader = self._make_loader()
        assert loader._process_json_file("/does/not/exist/file.json") is None

    def test_scalar_json_returns_none(self, tmp_path):
        loader = self._make_loader()
        f = tmp_path / "scalar.json"
        f.write_text("42", encoding="utf-8")
        assert loader._process_json_file(str(f)) is None

    def test_empty_array_returns_none(self, tmp_path):
        loader = self._make_loader()
        f = tmp_path / "empty.json"
        f.write_text("[]", encoding="utf-8")
        assert loader._process_json_file(str(f)) is None

    def test_array_entries_contain_error_messages(self, tmp_json_array_file, golden_dataset):
        loader = self._make_loader()
        docs = loader._process_json_file(tmp_json_array_file)
        for i, entry in enumerate(golden_dataset):
            assert entry["error_message"][:40] in docs[i].page_content

    def test_metadata_source_is_file_path(self, tmp_json_single_file):
        loader = self._make_loader()
        docs = loader._process_json_file(tmp_json_single_file)
        assert docs[0].metadata["source"] == tmp_json_single_file


# ─────────────────────────────────────────────────────────────
# LogLoader.load()
# ─────────────────────────────────────────────────────────────

class TestLoaderLoad:
    """LogLoader.load() integrates all sources and applies text splitting."""

    def test_empty_directory_returns_empty_list(self, tmp_path):
        loader = LogLoader(data_path=str(tmp_path))
        assert loader.load() == []

    def test_nonexistent_directory_returns_empty_list(self, tmp_path):
        missing = str(tmp_path / "nonexistent")
        loader = LogLoader(data_path=missing)
        result = loader.load()
        assert result == []

    def test_json_array_file_produces_chunks(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        assert len(chunks) > 0

    def test_all_chunks_are_document_instances(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        assert all(isinstance(c, Document) for c in chunks)

    def test_chunks_have_non_empty_content(self, data_dir_with_golden):
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        assert all(c.page_content.strip() for c in chunks)

    def test_chunk_size_does_not_exceed_limit(self, data_dir_with_golden):
        """Chunks must respect the configured CHUNK_SIZE (with some tolerance for word boundaries)."""
        from src.config import CHUNK_SIZE
        loader = LogLoader(data_path=data_dir_with_golden)
        chunks = loader.load()
        # Allow 5% overflow due to splitter behaviour on long words
        max_allowed = int(CHUNK_SIZE * 1.05)
        oversized = [c for c in chunks if len(c.page_content) > max_allowed]
        assert not oversized, f"{len(oversized)} chunks exceed the size limit"
