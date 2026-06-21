import pytest
from cryptography.fernet import Fernet

from src.jira.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("MNEMO_SECRET_KEY", Fernet.generate_key().decode())
    enc = encrypt_token("super-secret-token")
    assert enc != "super-secret-token"
    assert decrypt_token(enc) == "super-secret-token"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MNEMO_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encrypt_token("x")
