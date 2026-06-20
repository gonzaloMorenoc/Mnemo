from src.ingest.junit import parse_junit

JUNIT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite" tests="3" failures="1" errors="1">
  <testcase classname="LoginTest" name="test_login">
    <failure message="AssertionError: expected 200" type="AssertionError">at Login.py:10</failure>
  </testcase>
  <testcase classname="ApiTest" name="test_call">
    <error message="ConnectionError: refused" type="ConnectionError">at Api.py:22</error>
  </testcase>
  <testcase classname="OkTest" name="test_ok"/>
</testsuite>"""


def test_parse_junit_extracts_failures_and_errors():
    recs = parse_junit(JUNIT_XML, project="proj-b")
    assert len(recs) == 2
    names = {r.test_name for r in recs}
    assert names == {"LoginTest.test_login", "ApiTest.test_call"}
    login = next(r for r in recs if r.test_name == "LoginTest.test_login")
    assert login.source == "junit"
    assert login.project == "proj-b"
    assert login.error_type == "AssertionError"
    assert login.trace == "at Login.py:10"


def test_parse_junit_falls_back_to_message_for_type():
    xml = b'<testsuite><testcase name="t"><failure message="TimeoutException: x">trace</failure></testcase></testsuite>'
    recs = parse_junit(xml, project="p")
    assert recs[0].error_type == "TimeoutException"
    assert recs[0].test_name == "t"
