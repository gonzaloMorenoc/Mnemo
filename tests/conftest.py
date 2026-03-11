import pytest
import json
import os

EVAL_DATASET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "eval_dataset.json"
)


@pytest.fixture
def eval_dataset():
    """Loads the evaluation dataset with ground truth answers."""
    with open(EVAL_DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def single_sample(eval_dataset):
    """Returns a single test case for quick unit tests."""
    return eval_dataset[0]
