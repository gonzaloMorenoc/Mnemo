from src.ingest.models import strip_ansi, parse_error_type
from src.ingest.testng import parse_testng
from src.ingest.robot import parse_robot


def test_strip_ansi_removes_non_sgr_sequences():
    assert strip_ansi("\x1b[2K\x1b[1Gboom") == "boom"
    assert strip_ansi("\x1b[1Aup") == "up"


def test_strip_ansi_still_removes_sgr():
    assert strip_ansi("\x1b[31mError\x1b[0m: x") == "Error: x"


# ESC byte is 0x1b; we build the byte string programmatically so the XML
# stays well-formed when parsed (CDATA sections pass bytes through as-is).
_ESC = b"\x1b"

TESTNG_ANSI = (
    b"<?xml version=\"1.0\"?>\n"
    b"<testng-results>\n"
    b"  <suite name=\"S\"><test name=\"T\"><class name=\"C\">\n"
    b"    <test-method status=\"FAIL\" name=\"m\">\n"
    b"      <exception class=\"org.x.AssertionError\">\n"
    b"        <message><![CDATA[" + _ESC + b"[31mAssertionError" + _ESC + b"[0m: expected 1 got 2]]></message>\n"
    b"        <full-stacktrace><![CDATA[" + _ESC + b"[31mat C.m(C.java:1)" + _ESC + b"[0m]]></full-stacktrace>\n"
    b"      </exception>\n"
    b"    </test-method>\n"
    b"  </class></test></suite>\n"
    b"</testng-results>"
)


def test_testng_strips_ansi_from_message_and_trace():
    recs = parse_testng(TESTNG_ANSI, project="p")
    assert len(recs) == 1
    assert "\x1b" not in recs[0].message
    assert "AssertionError: expected 1 got 2" in recs[0].message
    assert recs[0].trace and "\x1b" not in recs[0].trace


ROBOT_ANSI = (
    b"<?xml version=\"1.0\"?>\n"
    b"<robot>\n"
    b"  <suite name=\"S\"><test name=\"Timeout\">\n"
    b"    <status status=\"FAIL\">" + _ESC + b"[31mAssertionError" + _ESC + b"[0m: boom</status>\n"
    b"  </test></suite>\n"
    b"</robot>"
)


def test_robot_strips_ansi_from_message():
    recs = parse_robot(ROBOT_ANSI, project="p")
    assert len(recs) == 1
    assert "\x1b" not in recs[0].message
    assert "AssertionError: boom" in recs[0].message
    assert recs[0].error_type == "AssertionError"
