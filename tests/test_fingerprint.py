from src.ingest.models import FailureRecord
from src.defects.fingerprint import normalize, fingerprint


def test_normalize_strips_volatile_parts():
    n = normalize("Timeout after 30000ms at 0xAB12 id 550e8400-e29b-41d4-a716-446655440000 /tmp/x/y.log")
    assert "<n>" in n and "<hex>" in n and "<uuid>" in n and "<path>" in n
    assert "30000" not in n


def _rec(msg, trace):
    return FailureRecord(test_name="t", error_type="TimeoutException", message=msg, trace=trace, project="p", source="allure")


def test_fingerprint_is_stable_across_volatile_differences():
    a = _rec("TimeoutException after 30000ms (id 550e8400-e29b-41d4-a716-446655440000)", "at Foo.java:42")
    b = _rec("TimeoutException after 45000ms (id 11111111-2222-3333-4444-555555555555)", "at Foo.java:99")
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_differs_for_different_errors():
    a = _rec("TimeoutException waiting for element", "at Foo.java:42")
    b = _rec("NullPointerException on submit", "at Bar.java:7")
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_is_hex_sha1():
    fp = fingerprint(_rec("X", None))
    assert len(fp) == 40 and all(c in "0123456789abcdef" for c in fp)
