import hashlib
import hmac

from src.ci.webhook_auth import verify_signature


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    body = b'{"a":1}'
    assert verify_signature(body, _sign(body, "s3cr3t"), "s3cr3t") is True


def test_tampered_body_fails():
    sig = _sign(b'{"a":1}', "s3cr3t")
    assert verify_signature(b'{"a":2}', sig, "s3cr3t") is False


def test_wrong_secret_fails():
    body = b'{"a":1}'
    assert verify_signature(body, _sign(body, "other"), "s3cr3t") is False


def test_missing_header_fails():
    assert verify_signature(b"{}", "", "s3cr3t") is False


def test_header_without_prefix_fails():
    body = b"{}"
    digest = hmac.new("s3cr3t".encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, digest, "s3cr3t") is False


def test_empty_secret_fails_closed():
    body = b"{}"
    assert verify_signature(body, _sign(body, ""), "") is False


def test_malformed_non_ascii_header_fails_closed():
    assert verify_signature(b"{}", "sha256=ñoño", "s3cr3t") is False
