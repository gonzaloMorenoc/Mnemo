import re
from typing import Dict, Iterator, List, Optional, Callable

from src.sanitizer_rules import PII_RULES, SECRET_RULES, redact_pem_blocks


# Defense-in-depth: the regex loop runs over chunks of at most this many
# characters, so its cost stays linear in the text length and no attacker-
# controlled payload can trigger catastrophic backtracking. EVERY chunk is
# sanitized: secrets in the tail of a long trace are redacted too (auditoría
# 23-nov, #17 — antes la cola a partir de 20.000 caracteres pasaba tal cual).
_MAX_SANITIZE_LEN = 20_000
# El corte se busca en un salto de línea (o, si no hay, un espacio) dentro de la
# segunda mitad del trozo: así un token no se parte entre dos trozos.
_MIN_CHUNK_FRACTION = 2

# ---------------------------------------------------------------------------
# Sensitive pattern definitions
#
# Each entry is: (compiled_regex, replacement, guard_fn | None)
#
# guard_fn(text) -> bool: called before the regex; if it returns False the
# substitution is skipped entirely (O(1) short-circuit).  This prevents even
# linear-time quadratic degradation on texts that obviously cannot match.
#
# Regex design rules (ReDoS prevention):
#  - '.' MUST NOT appear inside a character class that is immediately followed
#    by '\.', because the overlap creates catastrophic backtracking.
#  - Use dot-as-separator form: [chars]+ instead of [chars.]+
#    e.g. label\.label  not  [chars.]+\.label
# ---------------------------------------------------------------------------

# Email local-part: [A-Z0-9_%+-]+(?:\.[A-Z0-9_%+-]+)*
#   '.' only allowed as a separator between chunks (not inside the class)
# Email domain: [A-Z0-9-]+(?:\.[A-Z0-9-]+)+
#   same dot-separator pattern; no '.' inside the repeated class
_EMAIL_RE = re.compile(
    r"\b[A-Z0-9_%+-]+(?:\.[A-Z0-9_%+-]+)*@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+\b",
    re.IGNORECASE,
)

# Hostname *.internal: [a-z0-9-]+(?:\.[a-z0-9-]+)*
#   '.' only as a separator; class contains [a-z0-9-] with no '.'
_INTERNAL_RE = re.compile(
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.internal\b",
    re.IGNORECASE,
)

SENSITIVE_PATTERNS: List[tuple] = [
    # Secretos con forma reconocible primero: los patrones genéricos de abajo
    # (URL, ruta) partirían un token base64 que contenga «/».
    *SECRET_RULES,
    *PII_RULES,
    (_EMAIL_RE, "[REDACTED_EMAIL]", lambda t: "@" in t),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]", None),
    (
        re.compile(r"\b(?:https?://|ssh://|git@)[^\s'\"<>]+", re.IGNORECASE),
        "[REDACTED_URL]",
        lambda t: "://" in t or "git@" in t,
    ),
    (
        re.compile(
            r"\b(?:api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{8,}['\"]?",
            re.IGNORECASE,
        ),
        "[REDACTED_SECRET]",
        None,
    ),
    (re.compile(r"\b(?:[A-Za-z]:\\|/)[^\s'\"<>]{3,}"), "[REDACTED_PATH]", None),
    (
        re.compile(
            r"\b(?:user(?:name)?|account|login)\s*[:=]\s*['\"]?[A-Za-z0-9_.@-]{2,}['\"]?",
            re.IGNORECASE,
        ),
        "[REDACTED_USER]",
        None,
    ),
    (_INTERNAL_RE, "[REDACTED_HOSTNAME]", lambda t: "internal" in t.lower()),
]


TECH_TAG_RULES = {
    "playwright": re.compile(r"\bplaywright\b", re.IGNORECASE),
    "cucumber": re.compile(r"\bcucumber\b", re.IGNORECASE),
    "java": re.compile(r"\bjava\b|\bexception\b|\bjvm\b", re.IGNORECASE),
    "node": re.compile(r"\bnode(?:\.js)?\b|\bnpm\b", re.IGNORECASE),
    "python": re.compile(r"\bpython\b|\btraceback\b|\bpip\b", re.IGNORECASE),
    "pytest": re.compile(r"\bpytest\b", re.IGNORECASE),
    "selenium": re.compile(r"\bselenium\b|\bwebdriver\b", re.IGNORECASE),
    "kubernetes": re.compile(r"\bkubernetes\b|\bk8s\b", re.IGNORECASE),
    "docker": re.compile(r"\bdocker\b", re.IGNORECASE),
}

ERROR_TYPE_RULES = [
    ("timeout", re.compile(r"\btimeout|timed out\b", re.IGNORECASE)),
    ("assertion", re.compile(r"\bassert(?:ion)?\b", re.IGNORECASE)),
    ("null_pointer", re.compile(r"\bnullpointerexception\b|\bnone(type)?\b", re.IGNORECASE)),
    ("connection", re.compile(r"\bconnection(?:refused|reset|error)?\b", re.IGNORECASE)),
    ("auth", re.compile(r"\bunauthorized|forbidden|401|403|authentication\b", re.IGNORECASE)),
    ("not_found", re.compile(r"\b404\b|\bnot found\b", re.IGNORECASE)),
    ("syntax", re.compile(r"\bsyntaxerror\b|\bparse error\b", re.IGNORECASE)),
]


def _chunks(text: str, size: int = _MAX_SANITIZE_LEN) -> Iterator[str]:
    """Trocea por líneas en piezas de como mucho `size` caracteres (lineal)."""
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            floor = start + size // _MIN_CHUNK_FRACTION
            cut = text.rfind("\n", floor, end)
            if cut == -1:
                cut = text.rfind(" ", floor, end)
            if cut != -1:
                end = cut + 1
        yield text[start:end]
        start = end


def _sanitize_chunk(chunk: str) -> str:
    sanitized = chunk
    for pattern, replacement, guard in SENSITIVE_PATTERNS:
        if guard is not None and not guard(sanitized):
            continue
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def sanitize_text(text: str) -> str:
    """Redacta secretos y datos personales de TODO el texto, sea cual sea su longitud.

    Los bloques PEM se quitan primero sobre el texto entero (pueden cruzar el corte
    entre trozos); el resto de patrones corre trozo a trozo, con coste lineal."""
    if not text:
        return text
    without_pem = redact_pem_blocks(text)
    return "".join(_sanitize_chunk(chunk) for chunk in _chunks(without_pem))


def extract_tech_tags(text: str) -> List[str]:
    tags = [tag for tag, pattern in TECH_TAG_RULES.items() if pattern.search(text)]
    return sorted(set(tags))


def classify_error_type(text: str) -> Optional[str]:
    for error_type, pattern in ERROR_TYPE_RULES:
        if pattern.search(text):
            return error_type
    return None


def build_provenance_metadata(text: str) -> Dict[str, Optional[str]]:
    return {
        "tech_tags": extract_tech_tags(text),
        "error_type": classify_error_type(text),
    }
