import re
from dataclasses import dataclass
from typing import Optional

_ERR_RE = re.compile(r"([A-Za-z_][\w.]*(?:Error|Exception|Failure|Timeout))")


def parse_error_type(message: str) -> Optional[str]:
    """Best-effort: extrae el primer token tipo XxxError/XxxException del mensaje."""
    if not message:
        return None
    match = _ERR_RE.search(message)
    return match.group(1) if match else None


@dataclass
class FailureRecord:
    test_name: str
    error_type: Optional[str]
    message: str
    trace: Optional[str]
    project: str
    source: str  # "allure" | "junit"
