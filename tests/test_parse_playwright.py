import pytest

from src.ingest.playwright import parse_playwright

PLAYWRIGHT_JSON = b"""{
  "config": {},
  "suites": [
    {
      "title": "login.spec.ts",
      "specs": [
        {
          "title": "should login",
          "tests": [
            {
              "projectName": "chromium",
              "results": [
                {"status": "passed", "error": {}}
              ]
            }
          ]
        },
        {
          "title": "should logout",
          "tests": [
            {
              "projectName": "chromium",
              "results": [
                {"status": "failed",
                 "error": {"message": "\\u001b[31mError\\u001b[0m: expect(received).toBe(expected)",
                           "stack": "Error: boom\\n    at logout.spec.ts:10"}}
              ]
            }
          ]
        }
      ],
      "suites": []
    }
  ],
  "stats": {"expected": 1, "unexpected": 1}
}"""


def test_parse_playwright_returns_failed_results_without_ansi():
    recs = parse_playwright(PLAYWRIGHT_JSON, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "should logout (chromium)"
    assert "\x1b" not in r.message
    assert "expect(received).toBe(expected)" in r.message
    assert r.trace and "logout.spec.ts:10" in r.trace
    assert r.source == "playwright"


def test_parse_playwright_invalid_raises():
    with pytest.raises(ValueError):
        parse_playwright(b"{bad", project="p")
