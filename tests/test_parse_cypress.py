import pytest

from src.ingest.cypress import parse_cypress

MOCHAWESOME_JSON = b"""{
  "stats": {"suites": 1, "tests": 2, "passes": 1, "failures": 1},
  "results": [
    {
      "fullFile": "cypress/e2e/login.cy.js",
      "suites": [
        {
          "title": "Login",
          "tests": [
            {"title": "valid", "fullTitle": "Login valid", "state": "passed", "err": {}},
            {"title": "invalid", "fullTitle": "Login invalid", "state": "failed",
             "err": {"message": "AssertionError: expected 'a' to equal 'b'",
                     "estack": "AssertionError: boom\\n    at login.cy.js:8:10"}}
          ],
          "suites": []
        }
      ],
      "tests": []
    }
  ]
}"""


def test_parse_cypress_returns_failed_tests():
    recs = parse_cypress(MOCHAWESOME_JSON, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "Login invalid"
    assert "expected 'a' to equal 'b'" in r.message
    assert r.trace and "login.cy.js:8" in r.trace
    assert r.source == "cypress"


def test_parse_cypress_invalid_raises():
    with pytest.raises(ValueError):
        parse_cypress(b"nope", project="p")
