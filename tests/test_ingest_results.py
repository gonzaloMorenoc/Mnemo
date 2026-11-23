"""Resultados por test (pasados incluidos) extraídos del report subido por /ci/ingest.

Sin ellos, las señales del triaje `retry_passed_in_run` e `intermittent_same_sha`
salen siempre falsas en la ingesta por token (auditoría 23-nov, #5). El nombre del
test DEBE coincidir con el que produce el parser de fallos del mismo formato: el
triaje cruza `failures.test_name` con `test_results.test_name`.
"""
import json

from src.ingest.cypress import parse_cypress
from src.ingest.junit import parse_junit
from src.ingest.playwright import parse_playwright
from src.ingest.results import extract_results

_JUNIT = (
    b'<testsuite tests="5" failures="1" skipped="1">'
    b'<testcase classname="C" name="ok"/>'
    b'<testcase classname="C" name="ko"><failure message="AssertionError: x">t</failure></testcase>'
    b'<testcase classname="C" name="skip"><skipped/></testcase>'
    b'<testcase classname="C" name="flaky"><flakyFailure message="boom"/></testcase>'
    b'<testcase classname="C" name="rerun"><failure message="e"/><rerunFailure message="e"/></testcase>'
    b"</testsuite>"
)


def _by_name(results):
    return {r["test_name"]: r for r in results}


def test_junit_results_include_passed_and_retries():
    res = _by_name(extract_results("junit", _JUNIT))
    assert res["C.ok"] == {"test_name": "C.ok", "status": "pass", "retried": False}
    assert res["C.ko"]["status"] == "fail"
    assert res["C.skip"]["status"] == "skipped"
    # Surefire: flakyFailure = falló y pasó al reintentar
    assert res["C.flaky"] == {"test_name": "C.flaky", "status": "flaky", "retried": True}
    # rerunFailure = se reintentó y siguió fallando
    assert res["C.rerun"] == {"test_name": "C.rerun", "status": "fail", "retried": True}


def test_junit_result_names_match_failure_parser():
    failed = {r.test_name for r in parse_junit(_JUNIT, project="p")}
    results = {r["test_name"] for r in extract_results("junit", _JUNIT)
               if r["status"] == "fail"}
    assert results == failed


def _pw_test(title, status, results, project="chromium"):
    return {"title": title, "tests": [{"projectName": project, "status": status,
                                       "results": results}]}


def test_playwright_results_status_and_retries():
    report = {"suites": [{"specs": [
        _pw_test("ok", "expected", [{"status": "passed"}]),
        _pw_test("retry-ok", "flaky", [{"status": "failed", "error": {"message": "x"}},
                                       {"status": "passed"}]),
        _pw_test("ko", "unexpected", [{"status": "failed", "error": {"message": "Error: y"}}]),
        _pw_test("skip", "skipped", [{"status": "skipped"}]),
    ], "suites": []}]}
    data = json.dumps(report).encode()
    res = _by_name(extract_results("playwright", data))
    assert res["ok (chromium)"] == {"test_name": "ok (chromium)", "status": "pass",
                                    "retried": False}
    assert res["retry-ok (chromium)"]["status"] == "flaky"
    assert res["retry-ok (chromium)"]["retried"] is True
    assert res["ko (chromium)"]["status"] == "fail"
    assert res["skip (chromium)"]["status"] == "skipped"
    failed = {r.test_name for r in parse_playwright(data, project="p")}
    assert "ko (chromium)" in failed


def test_cypress_results():
    report = {"results": [{"tests": [
        {"fullTitle": "A ok", "state": "passed"},
        {"fullTitle": "A ko", "state": "failed", "err": {"message": "boom"}},
        {"fullTitle": "A pend", "state": "pending"},
    ], "suites": []}]}
    data = json.dumps(report).encode()
    res = _by_name(extract_results("cypress", data))
    assert res["A ok"]["status"] == "pass"
    assert res["A ko"]["status"] == "fail"
    assert res["A pend"]["status"] == "skipped"
    assert {r.test_name for r in parse_cypress(data, project="p")} == {"A ko"}


def test_allure_results():
    data = json.dumps([
        {"name": "a", "status": "passed"},
        {"name": "b", "status": "broken"},
        {"name": "c", "status": "skipped"},
    ]).encode()
    res = _by_name(extract_results("allure", data))
    assert [res[n]["status"] for n in ("a", "b", "c")] == ["pass", "fail", "skipped"]


def test_unsupported_or_broken_report_yields_no_results():
    assert extract_results("robot", b"<robot/>") == []
    assert extract_results("junit", b"<no-cierra") == []
    assert extract_results("playwright", b"{no json") == []
    assert extract_results("desconocido", b"x") == []
