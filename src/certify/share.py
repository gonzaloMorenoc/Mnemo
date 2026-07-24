"""Sobre compartible del acta: los bytes del enlace los produce quien firma."""
import base64
import json
from typing import Any, Dict

from src.certify.signing import canonical_json

# Tamaño máximo del sobre en base64. El acta NO es de tamaño fijo: `evidence`
# lleva una entrada por fallo triado. Por encima de esto el enlace deja de ser
# usable (correo y chat truncan enlaces largos) y es mejor no ofrecerlo.
MAX_SHARE_BYTES = 8192


def share_blob(cert: Dict[str, Any], signature: str) -> str:
    """Acta empaquetada para viajar en el fragmento de una URL (base64url sin padding).

    El sobre se construye por CONCATENACIÓN de bytes sobre el canónico ya firmado
    —nunca re-serializando el acta— para que lo que viaja parsee exactamente al
    objeto que se firmó. Cadena vacía si no cabe en un enlace usable.
    """
    envelope = (b'{"canonical_json":' + canonical_json(cert)
                + b',"signature":' + json.dumps(signature).encode("utf-8") + b'}')
    blob = base64.urlsafe_b64encode(envelope).decode("ascii").rstrip("=")
    return "" if len(blob) > MAX_SHARE_BYTES else blob
