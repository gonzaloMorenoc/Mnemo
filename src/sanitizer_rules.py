"""Reglas adicionales del sanitizer: secretos tipo gitleaks y datos personales de ES.

Auditoría 23-nov (#17 / H5): el sanitizer original no redactaba tokens Bearer/JWT,
Basic, claves AWS, tokens de GitHub, bloques PEM, DNI/NIE, IBAN ni teléfonos.

Diseño:
- Los datos personales con dígito de control (DNI, NIE, IBAN) se VALIDAN antes de
  redactar: sin eso, cualquier número de 8 cifras seguido de letra en una traza
  (un id de pedido) se perdería. Las trazas de stack son el contenido principal.
- Los teléfonos solo se redactan con prefijo internacional, con separadores de
  formato o junto a una palabra de contexto («teléfono», «móvil»…): un número de
  9 cifras suelto en una traza suele ser un id o una duración, no un teléfono.
- Los bloques PEM se quitan a mano (str.find), sobre el texto completo y antes de
  trocear: un bloque puede cruzar el corte entre trozos.
- Reglas anti-ReDoS de sanitizer.py: cuantificadores acotados y sin solapamiento
  entre una clase repetida y el separador que la sigue.
"""
import re
from typing import Callable, List, Optional, Tuple, Union

Replacement = Union[str, Callable[["re.Match[str]"], str]]
Rule = Tuple["re.Pattern[str]", Replacement, Optional[Callable[[str], bool]]]

# ---------------------------------------------------------------------------
# Bloques PEM
# ---------------------------------------------------------------------------

_PEM_BEGIN = "-----BEGIN "
_PEM_END = "-----END "
_PEM_DASHES = "-----"
_PEM_LABEL_MAX = 80          # «ENCRYPTED PRIVATE KEY», «CERTIFICATE»…
_PEM_REPLACEMENT = "[REDACTED_PRIVATE_KEY]"
_BASE64_LINE_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def _pem_block_end(text: str, begin: int) -> int:
    """Índice tras el final del bloque PEM que empieza en `begin`.

    Con cierre `-----END …-----`: justo tras él. Sin cierre (texto truncado): tras la
    línea de cabecera y las líneas siguientes que sean solo base64."""
    header_close = text.find(_PEM_DASHES, begin + len(_PEM_BEGIN))
    if header_close == -1 or header_close - begin > _PEM_LABEL_MAX + len(_PEM_BEGIN):
        return begin + len(_PEM_BEGIN)
    end_marker = text.find(_PEM_END, header_close)
    if end_marker != -1:
        footer_close = text.find(_PEM_DASHES, end_marker + len(_PEM_END))
        if footer_close != -1 and footer_close - end_marker <= _PEM_LABEL_MAX + len(_PEM_END):
            return footer_close + len(_PEM_DASHES)
    return _skip_base64_lines(text, header_close + len(_PEM_DASHES))


def _skip_base64_lines(text: str, pos: int) -> int:
    """Avanza sobre las líneas que son solo base64 (cuerpo de un PEM sin cierre)."""
    while pos < len(text):
        newline = text.find("\n", pos + 1)
        line_end = len(text) if newline == -1 else newline
        line = text[pos:line_end].strip()
        if line and not _BASE64_LINE_RE.match(line):
            return pos
        pos = line_end
    return pos


def redact_pem_blocks(text: str) -> str:
    """Sustituye cada bloque PEM por un marcador. Lineal en la longitud del texto."""
    if _PEM_BEGIN not in text:
        return text
    parts: List[str] = []
    cursor = 0
    while True:
        begin = text.find(_PEM_BEGIN, cursor)
        if begin == -1:
            break
        end = _pem_block_end(text, begin)
        parts.append(text[cursor:begin])
        parts.append(_PEM_REPLACEMENT)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


# ---------------------------------------------------------------------------
# Dígitos de control (DNI/NIE, IBAN)
# ---------------------------------------------------------------------------

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIX = {"X": "0", "Y": "1", "Z": "2"}
_IBAN_MODULUS = 97


def _dni_valid(number: str, letter: str) -> bool:
    return _DNI_LETTERS[int(number) % len(_DNI_LETTERS)] == letter.upper()


def _redact_dni(match: "re.Match[str]") -> str:
    ok = _dni_valid(match.group("num"), match.group("letter"))
    return "[REDACTED_DNI]" if ok else match.group(0)


def _redact_nie(match: "re.Match[str]") -> str:
    number = _NIE_PREFIX[match.group("prefix").upper()] + match.group("num")
    ok = _dni_valid(number, match.group("letter"))
    return "[REDACTED_NIE]" if ok else match.group(0)


def _iban_valid(raw: str) -> bool:
    compact = raw.replace(" ", "").upper()
    rearranged = compact[4:] + compact[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % _IBAN_MODULUS == 1


def _redact_iban(match: "re.Match[str]") -> str:
    return "[REDACTED_IBAN]" if _iban_valid(match.group(0)) else match.group(0)


# ---------------------------------------------------------------------------
# Patrones
# ---------------------------------------------------------------------------

# Un token «parece secreto» si tiene un dígito, un símbolo base64 o una mayúscula
# interior: así «Basic authentication» o «Bearer token missing» no se tocan.
_SECRETISH = r"(?=[A-Za-z0-9._~+/-]*(?:[0-9+/=_~.-]|[a-z][A-Z]))"

SECRET_RULES: List[Rule] = [
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,4096}\.eyJ[A-Za-z0-9_-]{5,8192}\.[A-Za-z0-9_-]{0,4096}"),
        "[REDACTED_JWT]",
        lambda t: "eyJ" in t,
    ),
    (
        re.compile(r"\b(Bearer)\s+" + _SECRETISH + r"[A-Za-z0-9._~+/-]{16,4096}=*", re.IGNORECASE),
        r"\1 [REDACTED_TOKEN]",
        lambda t: "earer" in t,
    ),
    (
        re.compile(r"\b(Basic)\s+" + _SECRETISH + r"[A-Za-z0-9+/]{12,4096}={0,2}"),
        r"\1 [REDACTED_TOKEN]",
        lambda t: "Basic" in t,
    ),
    (
        re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[A-Z0-9]{16}\b"),
        "[REDACTED_AWS_KEY]",
        None,
    ),
    (
        re.compile(r"\baws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", re.IGNORECASE),
        "[REDACTED_SECRET]",
        lambda t: "secret_access" in t.lower(),
    ),
    (
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b"),
        "[REDACTED_GITHUB_TOKEN]",
        lambda t: "gh" in t or "github_pat_" in t,
    ),
    (
        # Credenciales embebidas en una URL de cualquier esquema (postgresql://u:p@h).
        re.compile(r"\b([a-z][a-z0-9+-]{1,20}://)[^\s:/@'\"<>]{1,256}:[^\s@'\"<>/]{1,256}@",
                   re.IGNORECASE),
        r"\1[REDACTED_CREDENTIALS]@",
        lambda t: "://" in t,
    ),
]

_PHONE_SEP = r"[ .-]"
_PHONE_CONTEXT = r"(?:tel[eé]fono|tel[eé]f|tlf|tfno|tel|m[oó]vil|phone|mobile)"

PII_RULES: List[Rule] = [
    (
        re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b"),
        _redact_iban,
        None,
    ),
    (
        re.compile(r"\b(?P<prefix>[XYZ])[- ]?(?P<num>\d{7})[- ]?(?P<letter>[A-Z])\b", re.IGNORECASE),
        _redact_nie,
        None,
    ),
    (
        re.compile(r"\b(?P<num>\d{8})[- ]?(?P<letter>[A-Z])\b", re.IGNORECASE),
        _redact_dni,
        None,
    ),
    (
        # Prefijo internacional (+34 …, +1 …) o 0034.
        re.compile(r"(?:\+|\b0034)(?:\d" + _PHONE_SEP + r"?){8,14}\d\b"),
        "[REDACTED_PHONE]",
        lambda t: "+" in t or "0034" in t,
    ),
    (
        # Nacional con separadores: 612 345 678 · 612-345-678 · 912 34 56 78
        re.compile(r"\b[6789]\d{2}(?:" + _PHONE_SEP + r"\d{3}){2}\b"
                   r"|\b[6789]\d{2}(?:" + _PHONE_SEP + r"\d{2}){3}\b"),
        "[REDACTED_PHONE]",
        None,
    ),
    (
        # 9 cifras seguidas solo junto a una palabra de contexto.
        re.compile(r"\b(" + _PHONE_CONTEXT + r"\.?\s{0,3}[:=]?\s{0,3})[6789]\d{8}\b", re.IGNORECASE),
        r"\1[REDACTED_PHONE]",
        None,
    ),
]
