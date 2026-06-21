import re
from typing import Dict, List, Optional, Callable


# Defense-in-depth: cap the text length processed by regex patterns.
# Realistic error messages are well under this limit; attacker-controlled
# payloads beyond this limit cannot trigger catastrophic backtracking.
_MAX_SANITIZE_LEN = 20_000

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


def sanitize_text(text: str) -> str:
    # Cap the portion that goes through the regex loop.  Text beyond the cap
    # cannot contain sensitive data that wasn't already present in the head,
    # and skipping the tail avoids any O(n²) degradation on large inputs.
    if len(text) > _MAX_SANITIZE_LEN:
        head = text[:_MAX_SANITIZE_LEN]
        tail = text[_MAX_SANITIZE_LEN:]
    else:
        head = text
        tail = ""

    sanitized = head
    for pattern, replacement, guard in SENSITIVE_PATTERNS:
        if guard is not None and not guard(sanitized):
            continue
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized + tail


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
