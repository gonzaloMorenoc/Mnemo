"""
Shared fixtures for the SmartErrorDebugger test suite.
"""
import json
import os
import pytest

GOLDEN_DATASET_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "qa_test_errors.json"
)


@pytest.fixture(scope="session")
def golden_dataset():
    """The 5 canonical QA errors with known solutions, used as the evaluation ground truth."""
    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def tmp_json_array_file(tmp_path, golden_dataset):
    """A temp file containing the golden dataset as a JSON array."""
    path = tmp_path / "test_errors.json"
    path.write_text(json.dumps(golden_dataset), encoding="utf-8")
    return str(path)


@pytest.fixture
def tmp_json_single_file(tmp_path, golden_dataset):
    """A temp file containing a single golden dataset entry as a JSON object."""
    path = tmp_path / "single_error.json"
    path.write_text(json.dumps(golden_dataset[0]), encoding="utf-8")
    return str(path)


@pytest.fixture
def data_dir_with_golden(tmp_path, golden_dataset):
    """A temp data directory pre-populated with the golden dataset JSON."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "qa_test_errors.json").write_text(
        json.dumps(golden_dataset), encoding="utf-8"
    )
    return str(logs_dir)
