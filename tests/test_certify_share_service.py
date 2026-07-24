import base64
import json
from unittest.mock import MagicMock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.certify.service import CertificateService
from src.certify.signing import canonical_json, sign

_CERT = {
    "schema": "mnemo.cert.v3",
    "disclaimer": "La evaluación es una señal asistida.",
    "verdict": "apto", "risk_score": 0,
    "self_eval": {"engine_calibration": {"tenant_accuracy": 0.0, "n_corrections": 0}},
}


def _keys():
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    pub = sk.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def _service(cert_repo, priv, pub):
    return CertificateService(repo=MagicMock(), cert_repo=cert_repo, private_key=priv,
                              public_key=pub, mnemo_version="1.0", model_version="m1")


def _decode(blob: str) -> str:
    return base64.urlsafe_b64decode(blob + "=" * ((4 - len(blob) % 4) % 4)).decode("utf-8")


def test_get_adjunta_un_share_que_el_propio_servicio_verifica():
    priv, pub = _keys()
    cert_repo = MagicMock()
    cert_repo.get_certificate.return_value = {
        "id": "c1", "run_id": "r1", "org_id": "o1", "canonical_json": _CERT,
        "signature": sign(canonical_json(_CERT), priv), "verdict": "apto",
        "risk_score": 0, "sign_offs": [], "mnemo_version": "1.0",
        "model_version": "m1", "created_at": "2026-07-24T00:00:00Z",
    }
    svc = _service(cert_repo, priv, pub)

    got = svc.get(user_id="u1", run_id="r1")

    body = json.loads(_decode(got["share"]))
    assert svc.verify_payload(cert=body["canonical_json"], signature=body["signature"]) is True
    # No se pierde nada de lo que ya devolvía.
    assert got["run_id"] == "r1" and got["verdict"] == "apto"


def test_get_sin_acta_sigue_devolviendo_none():
    priv, pub = _keys()
    cert_repo = MagicMock()
    cert_repo.get_certificate.return_value = None
    assert _service(cert_repo, priv, pub).get(user_id="u1", run_id="r1") is None


def test_generate_devuelve_share_no_vacio():
    priv, pub = _keys()
    repo = MagicMock()
    repo.get_triage_for_run.return_value = []
    repo.count_failures_for_run.return_value = 0
    repo.get_calibration_metrics.return_value = {}
    cert_repo = MagicMock()
    cert_repo.get_run_meta.return_value = {
        "org_id": "o1", "project": "p", "commit_sha": "abc",
        "manifest": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "complete": True},
    }
    svc = CertificateService(repo=repo, cert_repo=cert_repo, private_key=priv,
                             public_key=pub, mnemo_version="1.0", model_version="m1")

    got = svc.generate(user_id="u1", run_id="r1", created_at="2026-07-24T00:00:00Z")

    body = json.loads(_decode(got["share"]))
    assert svc.verify_payload(cert=body["canonical_json"], signature=body["signature"]) is True


def test_endpoint_propaga_share_al_response():
    from src.api_v2 import get_certificate_v2

    service = MagicMock()
    service.get.return_value = {"run_id": "r1", "verdict": "apto", "risk_score": 0,
                                "canonical_json": _CERT, "signature": "sig",
                                "created_at": "2026-07-24T00:00:00Z", "share": "BLOB"}
    resp = get_certificate_v2("r1", user=MagicMock(user_id="u1"), service=service)
    assert resp.share == "BLOB"
