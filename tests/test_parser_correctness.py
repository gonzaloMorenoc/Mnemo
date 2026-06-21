from src.ingest.testng import parse_testng
from src.ingest.cypress import parse_cypress
from src.ingest.playwright import parse_playwright


TESTNG_CONFIG = b"""<?xml version="1.0"?>
<testng-results>
  <suite name="S"><test name="T"><class name="C">
    <test-method status="FAIL" name="setUp" is-config="true">
      <exception class="E"><message><![CDATA[fixture boom]]></message></exception>
    </test-method>
    <test-method status="FAIL" name="realTest">
      <exception class="E"><message><![CDATA[real boom]]></message></exception>
    </test-method>
  </class></test></suite>
</testng-results>"""


def test_testng_skips_config_methods():
    recs = parse_testng(TESTNG_CONFIG, project="p")
    assert len(recs) == 1
    assert recs[0].test_name == "C.realTest"


CYPRESS_PENDING_ERR = b"""{
  "stats": {}, "results": [{"suites": [{"tests": [
    {"title": "pend", "fullTitle": "S pend", "state": "pending",
     "err": {"message": "beforeEach failed"}},
    {"title": "ok", "fullTitle": "S ok", "state": "passed", "err": {}}
  ], "suites": []}], "tests": []}]
}"""


def test_cypress_ignores_pending_with_err():
    recs = parse_cypress(CYPRESS_PENDING_ERR, project="p")
    assert recs == []


PLAYWRIGHT_RETRY = b"""{
  "suites": [{"title": "f.spec.ts", "specs": [
    {"title": "flaky", "tests": [{"projectName": "chromium", "results": [
      {"status": "failed", "error": {"message": "first try"}},
      {"status": "passed", "error": {}}
    ]}]},
    {"title": "broken", "tests": [{"projectName": "chromium", "results": [
      {"status": "failed", "error": {"message": "try1"}},
      {"status": "failed", "error": {"message": "try2 final"}}
    ]}]}
  ], "suites": []}], "stats": {}
}"""


def test_playwright_counts_only_final_attempt():
    recs = parse_playwright(PLAYWRIGHT_RETRY, project="p")
    # flaky (passed on retry) -> no record; broken (failed finally) -> 1 record with final message
    assert len(recs) == 1
    assert "try2 final" in recs[0].message
