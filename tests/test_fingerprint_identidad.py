"""Huella de defecto v2 (auditoría 23-nov, #3): identidad del test + normalización
propia, independiente del saneador de privacidad.

Reproduce los dos escenarios de la auditoría: Go con `message="Failed"` y
Playwright con URLs distintas que el saneador colapsaba a [REDACTED_URL].
"""
from dataclasses import replace

from src.defects.fingerprint import (
    failure_summary,
    fingerprint,
    is_informative,
    normalize_volatile,
    failing_test_identity,
)
from src.ingest.junit import parse_junit
from src.ingest.models import FailureRecord
from src.sanitizer import sanitize_text


def _rec(msg, trace=None, *, test_name="t", error_type="Error", file=None, source="playwright"):
    return FailureRecord(test_name=test_name, error_type=error_type, message=msg,
                         trace=trace, project="p", source=source, file=file)


_GO = b'''<testsuites><testsuite name="pkg/a" tests="2" failures="2">
<testcase classname="pkg/a" name="TestLogin"><failure message="Failed" type="">    login_test.go:12: expected 200, got 500</failure></testcase>
<testcase classname="pkg/b" name="TestPayment"><failure message="Failed" type="">    payment_test.go:40: balance mismatch</failure></testcase>
</testsuite></testsuites>'''


def test_go_generic_failed_messages_do_not_share_fingerprint():
    a, b = parse_junit(_GO, project="p")
    assert fingerprint(a) != fingerprint(b)


def test_same_message_different_tests_differ():
    a = _rec("Error: expect(received).toBe(expected)", test_name="Cart.adds item")
    b = _rec("Error: expect(received).toBe(expected)", test_name="Auth.logs in")
    assert fingerprint(a) != fingerprint(b)


def test_urls_that_sanitizer_redacts_still_distinguish_defects():
    a = _rec("Expected: https://shop.example.com/checkout Received: https://shop.example.com/login",
             "    at /home/runner/work/app/tests/flow.spec.ts:42:7", test_name="flow")
    b = _rec("Expected: https://shop.example.com/cart Received: https://shop.example.com/500",
             "    at /home/runner/work/app/tests/flow.spec.ts:10:3", test_name="flow")
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_does_not_depend_on_the_sanitizer():
    """Si se calcula sobre el texto crudo, sanear antes o no da huellas DISTINTAS:
    la huella del ingestor es la del crudo (la ingesta la calcula antes de sanear)."""
    raw = _rec("Expected https://a.example.com/checkout got https://a.example.com/login")
    sanitized = replace(raw, message=sanitize_text(raw.message))
    other_raw = _rec("Expected https://a.example.com/cart got https://a.example.com/500")
    other_sanitized = replace(other_raw, message=sanitize_text(other_raw.message))
    assert fingerprint(sanitized) == fingerprint(other_sanitized)  # el bug viejo
    assert fingerprint(raw) != fingerprint(other_raw)              # la huella buena


def test_same_defect_is_stable_across_volatile_parts_and_machines():
    a = _rec("Order 1234 failed at 2026-11-23T10:00:01.123Z id=deadbeefcafe0042 req 550e8400-e29b-41d4-a716-446655440000",
             "    at /home/runner/work/app/tests/order.spec.ts:42:7", test_name="order [1]")
    b = _rec("Order 9876 failed at 2026-11-24T22:13:59Z id=0123456789abcdef req 11111111-2222-3333-4444-555555555555",
             "    at /Users/maria/dev/app/tests/order.spec.ts:51:3", test_name="order [2]")
    assert fingerprint(a) == fingerprint(b)


def test_test_identity_uses_file_basename_and_normalized_name():
    a = _rec("x", file="/ci/a/tests/cart.spec.ts", test_name="Cart adds item 3")
    b = _rec("x", file="C:\\agent\\tests\\cart.spec.ts", test_name="Cart adds item 7")
    assert failing_test_identity(a) == failing_test_identity(b)
    assert "cart.spec.ts" in failing_test_identity(a)


def test_normalize_volatile_keeps_url_paths_and_file_basenames():
    n = normalize_volatile("GET https://h.example.com/api/orders/42 at /home/u/p/tests/cart.spec.ts:10:3")
    assert "/api/orders/" in n and "cart.spec.ts" in n
    assert "/home/u" not in n and "42" not in n


def test_is_informative():
    assert not is_informative("")
    assert not is_informative("Failed")
    assert not is_informative("  failure ")
    assert not is_informative("123 456")
    assert is_informative("Timeout waiting for selector #pay")


def test_failure_summary_falls_back_to_first_trace_line():
    rec = _rec("", "\n  Error: expect(received).toBe(expected)\n    at cart.test.js:10:5")
    assert failure_summary(rec) == "Error: expect(received).toBe(expected)"
    assert failure_summary(_rec("Failed", None)) == "Failed"
    assert failure_summary(_rec("Timeout on pay", "x")) == "Timeout on pay"


def test_jira_issue_key_still_separates_issues():
    a = _rec("Login falla", test_name="PAY-1", source="jira")
    b = _rec("Login falla", test_name="PAY-2", source="jira")
    assert fingerprint(a) != fingerprint(b)
