import re
from dataclasses import dataclass
from typing import Optional

# Linear regex: dotted prefix built from explicit non-overlapping labels so
# [\w.]* cannot overlap the terminal Error/Exception/Failure/Timeout tokens,
# which eliminated catastrophic backtracking on strings like "a."*50000.
_ERR_RE = re.compile(r"((?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Failure|Timeout))")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_ANSI_BYTES_RE = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Elimina secuencias de escape ANSI (colores y cursor) de un texto."""
    return _ANSI_RE.sub("", text) if text else text


def strip_ansi_bytes(data: bytes) -> bytes:
    """Elimina secuencias de escape ANSI de datos en bytes (antes del parseo XML)."""
    return _ANSI_BYTES_RE.sub(b"", data) if data else data


_PARSE_MAX_LEN = 1_000


def parse_error_type(message: str) -> Optional[str]:
    """Best-effort: extrae el primer token tipo XxxError/XxxException del mensaje."""
    if not message:
        return None
    # Cap input length as defense-in-depth before regex matching.
    message = message[:_PARSE_MAX_LEN]
    match = _ERR_RE.search(message)
    return match.group(1) if match else None


@dataclass
class FailureRecord:
    test_name: str
    error_type: Optional[str]
    message: str
    trace: Optional[str]
    project: str
    source: str  # allure | junit | testng | cucumber | playwright | cypress | robot
    file: Optional[str] = None
    line: Optional[int] = None


def int_attr(el, name: str) -> int:
    """Lee un atributo entero de un elemento XML; 0 si falta o no es numérico."""
    try:
        return int(el.get(name) or 0)
    except (TypeError, ValueError):
        return 0


def synthetic_failure_record(*, project: str, source: str, declared: int) -> "FailureRecord":
    """Registro sintético para la RED DE SEGURIDAD: la cabecera del reporte declara
    fallos pero el parser no extrajo ninguno (hueco del parser / formato inesperado).
    Nunca se debe dejar pasar un run rojo como verde y firmar un acta 'apto'."""
    return FailureRecord(
        test_name="unknown (fallos declarados no extraídos)",
        error_type=None,
        message=(f"El reporte declara {declared} fallo(s) que el parser no pudo extraer; "
                 "revisa el reporte antes de confiar en un veredicto 'apto'."),
        trace=None,
        project=project,
        source=source,
    )
