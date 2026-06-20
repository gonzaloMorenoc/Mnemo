import pytest

from src.ingest.testng import parse_testng

TESTNG_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<testng-results failed="1" passed="1" total="2">
  <suite name="Suite">
    <test name="Test">
      <class name="com.example.LoginTest">
        <test-method status="PASS" name="testValidLogin"/>
        <test-method status="FAIL" name="testTimeout">
          <exception class="org.openqa.selenium.TimeoutException">
            <message><![CDATA[Expected condition failed: waited 30000ms]]></message>
            <full-stacktrace><![CDATA[org.openqa.selenium.TimeoutException: boom
	at com.example.LoginTest.testTimeout(LoginTest.java:42)]]></full-stacktrace>
          </exception>
        </test-method>
      </class>
    </test>
  </suite>
</testng-results>
"""


def test_parse_testng_returns_only_failures():
    recs = parse_testng(TESTNG_XML, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "com.example.LoginTest.testTimeout"
    assert r.error_type == "org.openqa.selenium.TimeoutException"
    assert "30000ms" in r.message
    assert r.trace and "LoginTest.java:42" in r.trace
    assert r.source == "testng"


def test_parse_testng_invalid_raises():
    with pytest.raises(ValueError):
        parse_testng(b"not xml", project="p")
