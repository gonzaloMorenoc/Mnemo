import re
from typing import Dict, List, Optional


SENSITIVE_PATTERNS = [
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IP]"),
    (re.compile(r"\b(?:https?://|ssh://|git@)[^\s'\"<>]+", re.IGNORECASE), "[REDACTED_URL]"),
    (
        re.compile(r"\b(?:api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{8,}['\"]?", re.IGNORECASE),
        "[REDACTED_SECRET]",
    ),
    (re.compile(r"\b(?:[A-Za-z]:\\|/)[^\s'\"<>]{3,}"), "[REDACTED_PATH]"),
    (
        re.compile(r"\b(?:user(?:name)?|account|login)\s*[:=]\s*['\"]?[A-Za-z0-9_.@-]{2,}['\"]?", re.IGNORECASE),
        "[REDACTED_USER]",
    ),
    (re.compile(r"\b[a-z0-9.-]+\.internal\b", re.IGNORECASE), "[REDACTED_HOSTNAME]"),
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
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


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
