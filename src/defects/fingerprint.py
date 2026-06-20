import hashlib
import re
from typing import Optional

from src.ingest.models import FailureRecord

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_PATH = re.compile(r"(?:/[\w.\-]+){2,}")
_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Elimina partes volatiles (uuid, hex, paths, numeros) para una firma estable."""
    if not text:
        return ""
    t = _UUID.sub("<uuid>", text)
    t = _HEX.sub("<hex>", t)
    t = _PATH.sub("<path>", t)
    t = _NUM.sub("<n>", t)
    t = _WS.sub(" ", t).strip().lower()
    return t


def _top_frame(trace: Optional[str]) -> str:
    if not trace:
        return ""
    for raw in trace.splitlines():
        line = raw.strip()
        if line.startswith("at ") or " line " in line or 'File "' in line:
            return normalize(line)
    return ""


def fingerprint(rec: FailureRecord) -> str:
    """Firma sha1 determinista: tipo de error + mensaje normalizado + top frame."""
    head = normalize(rec.message)[:200]
    basis = "|".join([(rec.error_type or "").lower(), head, _top_frame(rec.trace)])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
