import hashlib
import hmac

_PREFIX = "sha256="


def verify_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """Verifica la firma HMAC-SHA256 del cuerpo crudo del webhook (estilo GitHub).

    Fail-closed: si falta el secreto o la cabecera, devuelve False. La comparación
    usa hmac.compare_digest (tiempo constante) para no filtrar la firma esperada.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith(_PREFIX):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header[len(_PREFIX):]
    return hmac.compare_digest(expected, provided)
