from src.ingest.models import FailureRecord, parse_error_type


def test_parse_error_type_finds_exception():
    assert parse_error_type("org.openqa.selenium.TimeoutException: wait 30s") == "org.openqa.selenium.TimeoutException"


def test_parse_error_type_finds_error():
    assert parse_error_type("AssertionError: expected 200 but got 500") == "AssertionError"


def test_parse_error_type_none_when_absent():
    assert parse_error_type("something went wrong") is None
    assert parse_error_type("") is None


def test_failure_record_fields():
    rec = FailureRecord(test_name="t", error_type=None, message="m", trace=None, project="p", source="allure")
    assert rec.test_name == "t" and rec.project == "p" and rec.source == "allure"
