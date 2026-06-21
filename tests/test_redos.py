import signal

import pytest

from src.sanitizer import sanitize_text
from src.ingest.models import parse_error_type


class _Timeout(Exception):
    pass


def _with_deadline(seconds, fn, *args):
    def _handler(signum, frame):
        raise _Timeout()
    old = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def test_sanitize_email_no_redos():
    _with_deadline(2.0, sanitize_text, "a@" + "a." * 50000)


def test_sanitize_internal_no_redos():
    _with_deadline(2.0, sanitize_text, "a." * 40000 + "internal")


def test_parse_error_type_no_redos():
    _with_deadline(2.0, parse_error_type, "a." * 50000)


def test_sanitize_still_redacts_email():
    assert "[REDACTED_EMAIL]" in sanitize_text("contacto: john.doe@example.com aqui")


def test_sanitize_still_redacts_internal():
    assert "[REDACTED_HOSTNAME]" in sanitize_text("host db01.internal down")


def test_parse_error_type_still_extracts():
    assert parse_error_type("java.lang.NullPointerException: x") == "java.lang.NullPointerException"
    assert parse_error_type("got a TimeoutException here") == "TimeoutException"
