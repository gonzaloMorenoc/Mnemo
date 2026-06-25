import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.certify.signing import canonical_json, sign, verify, SigningKeyMissing


def _keypair():
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv_pem, pub_pem


def test_canonical_json_is_key_order_stable():
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


def test_sign_then_verify_ok():
    priv, pub = _keypair()
    canonical = canonical_json({"verdict": "apto", "risk_score": 0})
    assert verify(canonical, sign(canonical, priv), pub) is True


def test_verify_fails_on_tamper():
    priv, pub = _keypair()
    sig = sign(canonical_json({"verdict": "apto"}), priv)
    assert verify(canonical_json({"verdict": "no-apto"}), sig, pub) is False


def test_verify_fails_on_bad_signature():
    _, pub = _keypair()
    assert verify(canonical_json({"a": 1}), "bm90LWEtc2ln", pub) is False


def test_sign_without_key_raises():
    with pytest.raises(SigningKeyMissing):
        sign(b"x", "")
