from unittest.mock import MagicMock

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if service is not None:
        app.dependency_overrides[api_v2.get_certificate_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_generate_returns_certificate():
    svc = MagicMock()
    svc.generate.return_value = {"run_id": "r1", "verdict": "apto", "risk_score": 0,
                                 "canonical_json": {"verdict": "apto"}, "signature": "sig",
                                 "created_at": "2026-06-25T00:00:00Z"}
    resp = _client(service=svc).post("/v2/certificates/run/r1")
    assert resp.status_code == 200 and resp.json()["verdict"] == "apto"


def test_generate_run_without_verdicts_is_422():
    svc = MagicMock()
    svc.generate.side_effect = ValueError("run sin veredictos de triaje")
    assert _client(service=svc).post("/v2/certificates/run/r1").status_code == 422


def test_generate_missing_key_is_503():
    from src.certify.signing import SigningKeyMissing
    svc = MagicMock()
    svc.generate.side_effect = SigningKeyMissing("no key")
    assert _client(service=svc).post("/v2/certificates/run/r1").status_code == 503


def test_get_certificate_404_when_absent():
    svc = MagicMock()
    svc.get.return_value = None
    assert _client(service=svc).get("/v2/certificates/r1").status_code == 404


def test_get_certificate_html():
    svc = MagicMock()
    svc.get.return_value = {
        "run_id": "r1", "verdict": "apto", "risk_score": 0, "signature": "sig",
        "canonical_json": {"verdict": "apto", "identity": {}, "breakdown": {}, "evidence": []},
        "created_at": "2026-06-25T00:00:00Z"}
    resp = _client(service=svc).get("/v2/certificates/r1/html")
    assert resp.status_code == 200 and "apto" in resp.text


def test_verify_endpoint_roundtrip():
    from src.certify.signing import canonical_json, sign, verify
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    cert = {"verdict": "apto"}
    sig = sign(canonical_json(cert), priv_pem)
    svc = MagicMock()
    svc.verify_payload.return_value = verify(canonical_json(cert), sig, pub_pem)
    resp = _client(service=svc).post("/v2/certificates/verify",
                                     json={"canonical_json": cert, "signature": sig})
    assert resp.status_code == 200 and resp.json()["valido"] is True


def test_verify_endpoint_real_crypto_true_and_false():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from src.certify.service import CertificateService
    from src.certify.signing import canonical_json, sign
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    svc = CertificateService(repo=MagicMock(), cert_repo=MagicMock(), private_key=priv_pem,
                             public_key=pub_pem, mnemo_version="0.4.0", model_version="m")
    cert = {"verdict": "apto", "risk_score": 0}
    sig = sign(canonical_json(cert), priv_pem)
    client = _client(service=svc)
    ok = client.post("/v2/certificates/verify", json={"canonical_json": cert, "signature": sig})
    assert ok.status_code == 200 and ok.json()["valido"] is True
    bad = client.post("/v2/certificates/verify",
                      json={"canonical_json": {"verdict": "no-apto"}, "signature": sig})
    assert bad.status_code == 200 and bad.json()["valido"] is False


def test_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/certificates/run/r1").status_code == 401


def test_pdf_requires_auth():
    assert _client(service=MagicMock(), with_user=False).get("/v2/certificates/r1/pdf").status_code == 401


def test_certificate_pdf_endpoint_returns_pdf():
    svc = MagicMock()
    svc.get.return_value = {
        "run_id": "r1", "verdict": "apto", "risk_score": 0, "signature": "sig",
        "canonical_json": {"verdict": "apto", "identity": {}, "breakdown": {}, "evidence": []},
        "created_at": "2026-06-25T00:00:00Z"}
    resp = _client(service=svc).get("/v2/certificates/r1/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.content[:5] == b"%PDF-"


def test_certificate_pdf_404_when_missing():
    svc = MagicMock()
    svc.get.return_value = None
    resp = _client(service=svc).get("/v2/certificates/nope/pdf")
    assert resp.status_code == 404
