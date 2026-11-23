"""Huella (firma) determinista de un fallo: la llave de su familia de defecto.

Versión 2 (auditoría 23-nov-2026, #3). La v1 tenía dos fallos que fusionaban
defectos distintos —y el nuevo heredaba etiqueta, razón y prior R0 del viejo—:
  - ignoraba QUÉ test fallaba: con mensajes genéricos (Go `message="Failed"`,
    Jest con mensaje vacío) todos los fallos de la org daban la misma huella;
  - se calculaba sobre el texto YA saneado: el saneador de privacidad convierte
    URLs, rutas e IPs en `[REDACTED_*]`, así que `/checkout→/login` y
    `/cart→/500` quedaban idénticos.

Ahora la huella:
  - se calcula sobre el texto CRUDO (la ingesta la pide antes de sanear) con una
    normalización PROPIA de partes volátiles (números, ids, hex, uuids, fechas,
    directorios de ficheros). No depende del saneador: ampliarlo no la cambia;
  - incluye la identidad del test (fichero sin directorio + nombre normalizado);
  - si el mensaje no dice nada, usa la primera línea con contenido de la traza.
Es un hash: no filtra nada de lo que el saneador protege.
"""
import hashlib
import ntpath
import re
from typing import Optional

from src.ingest.models import FailureRecord

# Prefijo de la base de la huella: cambiar la receta cambia todas las huellas, y
# una versión explícita deja claro en el código cuándo pasó.
SIGNATURE_VERSION = "v2"
MAX_SUMMARY_CHARS = 200
# Tope de entrada de la normalización (defensa ante ReDoS y trazas enormes): de
# lo normalizado solo entran en la huella MAX_SUMMARY_CHARS caracteres.
MAX_NORMALIZE_INPUT = 1_000
# Un mensaje cuenta como informativo con al menos estas letras tras quitar las
# partes volátiles y si no es una de las fórmulas genéricas de los reporters.
MIN_INFORMATIVE_LETTERS = 5
GENERIC_MESSAGES = frozenset({
    "failed", "failure", "fail", "error", "test failed", "assertion failed",
    "assertionerror", "assertion error", "exception", "failed test",
})

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_PATH = re.compile(r"(?:/[\w.\-]+){2,}")
_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")
_LETTER = re.compile(r"[^\W\d_]")

# v2: partes volátiles adicionales.
_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?\b")
# Ids hexadecimales sin 0x (shas de commit, ids de petición): ≥8 caracteres y al
# menos un dígito, para no tragarse palabras como «deadline» o «facade».
_LONG_HEX = re.compile(r"\b(?=[0-9a-fA-F]*\d)[0-9a-fA-F]{8,}\b")
# Ruta de FICHERO (acaba en nombre.ext): el directorio cambia de una máquina de
# CI a otra; el nombre del fichero identifica el defecto. Las rutas de URL
# (`/api/orders/42`) no acaban en extensión y se conservan.
_FILE_PATH = re.compile(r"(?:[A-Za-z]:)?(?:[\\/][\w.\-]+)*[\\/]([\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]\w{0,4})\b")
_FRAME_HINT = re.compile(r"[\w\-]+\.[A-Za-z]\w{0,4}:\d+")


def normalize(text: str) -> str:
    """Normalización v1 (se conserva por compatibilidad: ya no entra en la huella)."""
    if not text:
        return ""
    t = _UUID.sub("<uuid>", text)
    t = _HEX.sub("<hex>", t)
    t = _PATH.sub("<path>", t)
    t = _NUM.sub("<n>", t)
    t = _WS.sub(" ", t).strip().lower()
    return t


def normalize_volatile(text: Optional[str]) -> str:
    """Quita lo que cambia entre dos apariciones del MISMO defecto (uuids, fechas,
    hex, números, directorios de ficheros) y conserva lo que lo distingue (textos,
    rutas de URL, nombres de fichero). Independiente del saneador de privacidad."""
    if not text:
        return ""
    t = _UUID.sub("<uuid>", text[:MAX_NORMALIZE_INPUT])
    t = _TIMESTAMP.sub("<ts>", t)
    t = _HEX.sub("<hex>", t)
    t = _FILE_PATH.sub(r"\1", t)
    t = _LONG_HEX.sub("<hex>", t)
    t = _NUM.sub("<n>", t)
    return _WS.sub(" ", t).strip().lower()


def is_informative(message: Optional[str]) -> bool:
    """¿El mensaje distingue el fallo? No si está vacío, es una fórmula genérica
    («Failed») o, sin las partes volátiles, apenas le quedan letras."""
    norm = normalize_volatile(message)
    if not norm or norm.strip(" .:!") in GENERIC_MESSAGES:
        return False
    sin_volatiles = re.sub(r"<\w+>", "", norm)
    return len(_LETTER.findall(sin_volatiles)) >= MIN_INFORMATIVE_LETTERS


def _first_trace_line(trace: Optional[str]) -> str:
    for raw in (trace or "").splitlines():
        line = raw.strip()
        if line:
            return line
    return ""


def failure_summary(rec: FailureRecord) -> str:
    """Lo que dice el fallo: el mensaje si informa; si no, la primera línea con
    contenido de la traza (Jest y Go dejan ahí el texto real); si tampoco, el
    mensaje tal cual (puede ser vacío)."""
    if is_informative(rec.message):
        return rec.message.strip()
    return _first_trace_line(rec.trace) or (rec.message or "").strip()


def failing_test_identity(rec: FailureRecord) -> str:
    """Identidad estable del test: fichero sin directorio + nombre normalizado.
    Los números del nombre se igualan (parametrizaciones `[1]`, `[2]` = mismo test)."""
    file_name = ntpath.basename((rec.file or "").replace("/", "\\"))
    return f"{normalize_volatile(file_name)}::{normalize_volatile(rec.test_name)}"


def _top_frame(trace: Optional[str]) -> str:
    if not trace:
        return ""
    for raw in trace.splitlines():
        line = raw.strip()
        if (line.startswith("at ") or " line " in line or 'File "' in line
                or _FRAME_HINT.search(line)):
            return normalize_volatile(line)
    return ""


def fingerprint(rec: FailureRecord) -> str:
    """Firma sha1 determinista: versión | tipo de error | resumen normalizado |
    top frame | identidad del test. Calcúlala sobre el registro CRUDO.

    Para registros de fuente 'jira' se añade además la clave del issue sin
    normalizar: es el identificador único y no debe colapsar issues distintos.
    """
    parts = [
        SIGNATURE_VERSION,
        (rec.error_type or "").lower(),
        normalize_volatile(failure_summary(rec))[:MAX_SUMMARY_CHARS],
        _top_frame(rec.trace),
        failing_test_identity(rec),
    ]
    if getattr(rec, "source", "") == "jira":
        parts.append(rec.test_name or "")   # issue key, unique, not normalized
    basis = "|".join(parts)
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
