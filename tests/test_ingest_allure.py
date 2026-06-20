import json

from src.ingest.allure import parse_allure


def test_parse_allure_extracts_only_failures():
    data = json.dumps([
        {"name": "test_login", "status": "failed",
         "statusDetails": {"message": "TimeoutException: 30s", "trace": "at Foo.java:42"}},
        {"name": "test_ok", "status": "passed", "statusDetails": {}},
        {"name": "test_skip", "status": "skipped", "statusDetails": {}},
        {"name": "test_broken", "status": "broken",
         "statusDetails": {"message": "NullPointerException", "trace": "at Bar.java:7"}},
    ]).encode()
    recs = parse_allure(data, project="proj-a")
    assert len(recs) == 2
    names = {r.test_name for r in recs}
    assert names == {"test_login", "test_broken"}
    login = next(r for r in recs if r.test_name == "test_login")
    assert login.source == "allure"
    assert login.project == "proj-a"
    assert login.error_type == "TimeoutException"
    assert "30s" in login.message
    assert login.trace == "at Foo.java:42"


def test_parse_allure_accepts_single_object():
    data = json.dumps({"name": "t", "status": "failed", "statusDetails": {"message": "X"}}).encode()
    recs = parse_allure(data, project="p")
    assert len(recs) == 1 and recs[0].test_name == "t"


def test_parse_allure_handles_missing_fields():
    data = json.dumps([{"status": "failed"}]).encode()
    recs = parse_allure(data, project="p")
    assert len(recs) == 1
    assert recs[0].test_name == "unknown"
    assert recs[0].message == ""
    assert recs[0].trace is None
