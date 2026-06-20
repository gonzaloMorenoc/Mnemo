import pytest

from src.ingest.cucumber import parse_cucumber

CUCUMBER_JSON = b"""[
  {
    "keyword": "Feature",
    "name": "Login",
    "elements": [
      {
        "keyword": "Scenario",
        "name": "Invalid password",
        "steps": [
          {"keyword": "Given ", "name": "the user is on login", "result": {"status": "passed"}},
          {"keyword": "When ", "name": "submits wrong password",
           "result": {"status": "failed",
                      "error_message": "AssertionError: expected 200 but got 401\\n    at steps.js:12"}}
        ]
      }
    ]
  }
]"""


def test_parse_cucumber_returns_failed_steps():
    recs = parse_cucumber(CUCUMBER_JSON, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "Login / Invalid password"
    assert "expected 200 but got 401" in r.message
    assert r.error_type == "AssertionError"
    assert r.source == "cucumber"


def test_parse_cucumber_invalid_raises():
    with pytest.raises(ValueError):
        parse_cucumber(b"{not json", project="p")
