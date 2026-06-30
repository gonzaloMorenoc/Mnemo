"""Verificación del path JWKS de SupabaseJWTVerifier (producción).

Cubre el bug: Supabase emite JWT ES256 (claves EC); el verificador asumía RS256
(RSAAlgorithm.from_jwk) y lanzaba InvalidKeyError → 500. Ahora PyJWK soporta EC y RSA.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException

from src import config
from src.security import SupabaseJWTVerifier


def _ec_jwk():
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(priv.public_key()))
    pub["kid"], pub["alg"] = "ec-kid", "ES256"
    return priv, pub


def _rsa_jwk():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    pub["kid"], pub["alg"] = "rsa-kid", "RS256"
    return priv, pub


def _verifier_with(monkeypatch, jwk):
    """Verifier forzado al path JWKS (sin JWT_SECRET) con un JWKS fijo."""
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "")
    v = SupabaseJWTVerifier()
    monkeypatch.setattr(v, "_load_jwks", lambda: {"keys": [jwk]})
    return v


def _token(priv, alg, kid):
    return jwt.encode(
        {"sub": "user-1", "email": "a@b.c", "exp": int(time.time()) + 3600},
        priv, algorithm=alg, headers={"kid": kid},
    )


def test_es256_token_is_verified(monkeypatch):
    """El caso real de Supabase: JWT ES256 con clave EC → valida (antes daba 500)."""
    priv, jwk = _ec_jwk()
    v = _verifier_with(monkeypatch, jwk)
    user = v.verify(_token(priv, "ES256", "ec-kid"))
    assert user.user_id == "user-1"
    assert user.email == "a@b.c"


def test_rs256_token_still_verified(monkeypatch):
    """Regresión: las claves RSA/RS256 siguen funcionando."""
    priv, jwk = _rsa_jwk()
    v = _verifier_with(monkeypatch, jwk)
    user = v.verify(_token(priv, "RS256", "rsa-kid"))
    assert user.user_id == "user-1"


def test_wrong_signature_rejected(monkeypatch):
    """Firma con otra clave que la del JWKS → 401 (no 500)."""
    _, jwk = _ec_jwk()              # el JWKS publica esta clave pública
    other_priv, _ = _ec_jwk()      # pero el token se firma con otra
    v = _verifier_with(monkeypatch, jwk)
    with pytest.raises(HTTPException) as exc:
        v.verify(_token(other_priv, "ES256", "ec-kid"))
    assert exc.value.status_code == 401
