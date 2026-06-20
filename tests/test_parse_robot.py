import pytest

from src.ingest.robot import parse_robot

ROBOT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 6.0">
  <suite name="Login Tests" source="login.robot">
    <test name="Valid Login">
      <status status="PASS"/>
    </test>
    <test name="Timeout Login">
      <kw name="Wait Until Element Is Visible">
        <msg level="FAIL">Element 'id=foo' not visible after 30 seconds</msg>
        <status status="FAIL"/>
      </kw>
      <status status="FAIL">Element 'id=foo' not visible after 30 seconds</status>
    </test>
  </suite>
</robot>
"""


def test_parse_robot_returns_failed_tests():
    recs = parse_robot(ROBOT_XML, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "Timeout Login"
    assert "not visible after 30 seconds" in r.message
    assert r.source == "robot"


def test_parse_robot_invalid_raises():
    with pytest.raises(ValueError):
        parse_robot(b"<robot", project="p")
