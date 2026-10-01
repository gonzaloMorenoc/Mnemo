import pytest
from pydantic import ValidationError

from src.ci.models import CiRunArtifact, CiTestResult


def _artifact_dict():
    return {
        "project": "demo", "org_id": "org-1", "commit_sha": "abc123",
        "source": "playwright",
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html></html>"},
            {"test_name": "home", "status": "pass"},
        ],
    }


def test_parses_valid_artifact():
    art = CiRunArtifact.model_validate(_artifact_dict())
    assert art.project == "demo" and art.commit_sha == "abc123"
    assert len(art.tests) == 2
    assert art.tests[0].status == "fail" and art.tests[0].retried is False


def test_source_defaults_to_playwright():
    d = _artifact_dict()
    del d["source"]
    assert CiRunArtifact.model_validate(d).source == "playwright"


def test_rejects_bad_status():
    with pytest.raises(ValidationError):
        CiTestResult.model_validate({"test_name": "x", "status": "exploded"})


def test_rejects_missing_required():
    with pytest.raises(ValidationError):
        CiRunArtifact.model_validate({"project": "p", "tests": []})


def test_rejects_oversized_field():
    with pytest.raises(ValidationError):
        CiTestResult.model_validate({"test_name": "t", "status": "fail", "error_type": "x" * 501})


def test_run_uid_optional_default_none():
    art = CiRunArtifact.model_validate(
        {"project": "p", "org_id": "o", "commit_sha": "abc", "tests": []}
    )
    assert art.run_uid is None
    art2 = CiRunArtifact.model_validate(
        {"project": "p", "org_id": "o", "commit_sha": "abc", "run_uid": "u-123", "tests": []}
    )
    assert art2.run_uid == "u-123"


def test_rejects_source_outside_the_db_check():
    # test_runs.source tiene un CHECK (migración 005). Sin validarlo aquí, un CI
    # que mande otro valor llegaba al INSERT y moría con un 500 en vez de un 422.
    d = _artifact_dict()
    d["source"] = "mocha"
    with pytest.raises(ValidationError):
        CiRunArtifact.model_validate(d)


@pytest.mark.parametrize("source", ["allure", "junit", "testng", "cucumber",
                                    "playwright", "cypress", "robot"])
def test_accepts_every_report_format(source):
    d = _artifact_dict()
    d["source"] = source
    assert CiRunArtifact.model_validate(d).source == source
