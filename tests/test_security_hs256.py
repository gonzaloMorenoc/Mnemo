import jwt as pyjwt
import pytest

from src import config
from src.security import SupabaseJWTVerifier
from fastapi import HTTPException


def test_hs256_token_accepted_when_secret_set(monkeypatch):
    secret = "super-secret-jwt-token-with-at-least-32-characters-long"
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", secret)
    token = pyjwt.encode({"sub": "user-1", "email": "d@x.com"}, secret, algorithm="HS256")
    user = SupabaseJWTVerifier().verify(token)
    assert user.user_id == "user-1" and user.email == "d@x.com"


def test_hs256_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "the-real-secret-key-32-characters-min!!")
    bad = pyjwt.encode({"sub": "x"}, "a-different-wrong-secret-key-32-characters", algorithm="HS256")
    with pytest.raises(HTTPException):
        SupabaseJWTVerifier().verify(bad)
