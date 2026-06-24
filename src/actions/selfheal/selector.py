import re
from dataclasses import dataclass
from typing import Optional

_TESTID = re.compile(r"getByTestId\(\s*['\"]([^'\"]+)['\"]")
_ROLE = re.compile(r"getByRole\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*\{[^}]*?name:\s*['\"]([^'\"]+)['\"])?")
_TEXT = re.compile(r"getByText\(\s*['\"]([^'\"]+)['\"]")
_CSS = re.compile(r"locator\(\s*['\"]([^'\"]+)['\"]")


@dataclass
class BrokenSelector:
    kind: str            # css | testid | text | role
    value: str
    name: Optional[str] = None


def parse_broken_selector(error_message: str, trace: Optional[str] = None) -> Optional[BrokenSelector]:
    """Extrae el locator roto del error de Playwright (busca en mensaje + trace).
    Soporta getByTestId/getByRole/getByText/locator(css). None si no reconoce nada."""
    text = f"{error_message or ''}\n{trace or ''}"
    m = _TESTID.search(text)
    if m:
        return BrokenSelector(kind="testid", value=m.group(1))
    m = _ROLE.search(text)
    if m:
        return BrokenSelector(kind="role", value=m.group(1), name=m.group(2))
    m = _TEXT.search(text)
    if m:
        return BrokenSelector(kind="text", value=m.group(1))
    m = _CSS.search(text)
    if m:
        return BrokenSelector(kind="css", value=m.group(1))
    return None
