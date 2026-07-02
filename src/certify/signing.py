import base64
import hashlib
import json
from typing import Any, Dict

from cryptography.hazmat.primitives import serialization


class SigningKeyMissing(RuntimeError):
    """La clave privada de firma (MNEMO_SIGNING_PRIVATE_KEY) no está configurada."""


def key_id(public_key_pem: str) -> str:
    """Identificador determinista de la clave pública (SHA-256 truncado a 16 hex).

    Va dentro del acta firmada para que un verificador sepa qué clave usar (habilita
    rotación: certificados viejos siguen verificando con su clave). Cadena vacía si
    no hay clave configurada."""
    if not public_key_pem:
        return ""
    return hashlib.sha256(public_key_pem.strip().encode("utf-8")).hexdigest()[:16]


def canonical_json(cert: Dict[str, Any]) -> bytes:
    """Serialización canónica determinista: claves ordenadas, sin espacios, UTF-8."""
    return json.dumps(cert, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign(canonical: bytes, private_key_pem: str) -> str:
    if not private_key_pem:
        raise SigningKeyMissing("MNEMO_SIGNING_PRIVATE_KEY no configurada")
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    return base64.b64encode(key.sign(canonical)).decode("ascii")


def verify(canonical: bytes, signature_b64: str, public_key_pem: str) -> bool:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
        key.verify(base64.b64decode(signature_b64), canonical)
        return True
    except Exception:  # noqa: BLE001 — verificación booleana, cualquier fallo → False
        return False
