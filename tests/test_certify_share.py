import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.certify.share import MAX_SHARE_BYTES, share_blob
from src.certify.signing import canonical_json, sign, verify

# Los dos venenos del formato: un float redondo (Python firma "0.0", JS lo
# colapsa a "0") y acentos (el disclaimer se firma con ensure_ascii=False).
_CERT = {
    "schema": "mnemo.cert.v3",
    "disclaimer": "La evaluación es una señal asistida, no una garantía.",
    "verdict": "apto-con-reservas",
    "risk_score": 12,
    "identity": {"project": "checkout-suite", "key_id": "946152583e361f1e"},
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


def _decode(blob: str) -> str:
    """Lo que hace el navegador: base64url -> bytes -> texto UTF-8."""
    return base64.urlsafe_b64decode(blob + "=" * ((4 - len(blob) % 4) % 4)).decode("utf-8")


def test_share_blob_round_trip_verifica_con_la_firma_real():
    priv, pub = _keys()
    signature = sign(canonical_json(_CERT), priv)
    body = json.loads(_decode(share_blob(_CERT, signature)))
    assert verify(canonical_json(body["canonical_json"]), body["signature"], pub) is True


def test_share_blob_es_base64url_puro():
    # '+', '/' y '=' se malinterpretan en una URL; el sobre no puede contenerlos.
    assert set("+/=").isdisjoint(share_blob(_CERT, "sig"))


def test_acta_manipulada_no_verifica():
    priv, pub = _keys()
    signature = sign(canonical_json(_CERT), priv)
    body = json.loads(_decode(share_blob(_CERT, signature)))
    body["canonical_json"]["risk_score"] = 1  # "alguien retoca el acta"
    assert verify(canonical_json(body["canonical_json"]), body["signature"], pub) is False


def test_share_vacio_cuando_el_acta_no_cabe_en_un_enlace():
    grande = {**_CERT, "evidence": [{"failure_id": f"f{i}", "category": "real",
                                     "confidence": 0.9, "rule_applied": "R5_real_novel"}
                                    for i in range(500)]}
    assert share_blob(grande, "sig") == ""
    assert len(share_blob(_CERT, "sig")) < MAX_SHARE_BYTES
