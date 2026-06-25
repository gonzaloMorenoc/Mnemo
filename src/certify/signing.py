import base64
import json
from typing import Any, Dict

from cryptography.hazmat.primitives import serialization


class SigningKeyMissing(RuntimeError):
    """La clave privada de firma (MNEMO_SIGNING_PRIVATE_KEY) no está configurada."""


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
