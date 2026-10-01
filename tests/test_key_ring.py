"""Rotar la clave de firma no invalida las actas ya emitidas.

signing.key_id prometía que «certificados viejos siguen verificando con su clave»,
pero verify_payload solo probaba la clave actual: al rotar el 14-ago, todas las actas
anteriores pasaron a «Firma NO válida». Ahora la verificación elige la clave por el
key_id que va DENTRO del acta firmada, entre la actual y las retiradas."""
from unittest.mock import MagicMock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.certify.service import CertificateService, parse_public_keys
from src.certify.signing import canonical_json, key_id, sign


def _par():
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def _svc(pub_actual, retiradas=()):
    return CertificateService(repo=MagicMock(), cert_repo=MagicMock(), private_key="",
                              public_key=pub_actual, mnemo_version="t", model_version="t",
                              retired_public_keys=list(retiradas))


def _acta_release(priv, pub):
    cert = {"schema": "mnemo.cert.v3", "identity": {"key_id": key_id(pub)}, "verdict": "apto"}
    return cert, sign(canonical_json(cert), priv)


def _acta_traspaso(priv, pub):
    acta = {"schema": "mnemo.traspaso.v2", "key_id": key_id(pub), "project": "p"}
    return acta, sign(canonical_json(acta), priv)


def test_un_acta_firmada_con_una_clave_retirada_sigue_verificando():
    priv_vieja, pub_vieja = _par()
    _, pub_nueva = _par()
    for acta, firma in (_acta_release(priv_vieja, pub_vieja), _acta_traspaso(priv_vieja, pub_vieja)):
        assert _svc(pub_nueva, [pub_vieja]).verify_payload(cert=acta, signature=firma) is True
        # Sin la clave retirada en el anillo, no hay forma de comprobarla.
        assert _svc(pub_nueva).verify_payload(cert=acta, signature=firma) is False


def test_manipular_un_acta_vieja_sigue_dando_no_valida():
    priv_vieja, pub_vieja = _par()
    _, pub_nueva = _par()
    acta, firma = _acta_release(priv_vieja, pub_vieja)
    assert _svc(pub_nueva, [pub_vieja]).verify_payload(cert={**acta, "verdict": "no-apto"},
                                                        signature=firma) is False


def test_las_actas_con_la_clave_actual_verifican_como_siempre():
    priv, pub = _par()
    acta, firma = _acta_release(priv, pub)
    assert _svc(pub).verify_payload(cert=acta, signature=firma) is True


def test_parse_public_keys_separa_varios_pem():
    _, a = _par()
    _, b = _par()
    assert parse_public_keys(a + "\n" + b) == [a.strip(), b.strip()]
    assert parse_public_keys("") == []
