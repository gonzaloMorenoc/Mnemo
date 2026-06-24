from src.ci.mapping import to_failure_records
from src.ci.models import CiRunArtifact


def _art(tests):
    return CiRunArtifact.model_validate(
        {"project": "demo", "org_id": "o", "commit_sha": "sha", "tests": tests}
    )


def test_only_failed_and_flaky_become_records():
    art = _art([
        {"test_name": "a", "status": "pass"},
        {"test_name": "b", "status": "skipped"},
        {"test_name": "c", "status": "fail", "message": "AssertionError: nope"},
        {"test_name": "d", "status": "flaky", "message": "TimeoutError: x"},
    ])
    recs = to_failure_records(art)
    assert {r.test_name for r in recs} == {"c", "d"}


def test_excludes_failed_without_message():
    art = _art([{"test_name": "c", "status": "fail"}])
    assert to_failure_records(art) == []


def test_infers_error_type_when_missing():
    art = _art([{"test_name": "c", "status": "fail",
                 "message": "TimeoutError: locator not found"}])
    rec = to_failure_records(art)[0]
    assert rec.error_type == "TimeoutError"
    assert rec.project == "demo" and rec.source == "playwright"


def test_keeps_explicit_error_type():
    art = _art([{"test_name": "c", "status": "fail",
                 "error_type": "CustomError", "message": "boom"}])
    assert to_failure_records(art)[0].error_type == "CustomError"


def test_carries_file_and_line():
    art = _art([{"test_name": "c", "status": "fail", "message": "boom",
                 "file": "tests/checkout.spec.ts", "line": 42}])
    rec = to_failure_records(art)[0]
    assert rec.file == "tests/checkout.spec.ts" and rec.line == 42


def test_file_line_default_none_when_absent():
    art = _art([{"test_name": "c", "status": "fail", "message": "boom"}])
    rec = to_failure_records(art)[0]
    assert rec.file is None and rec.line is None
