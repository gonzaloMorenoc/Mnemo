import re
from dataclasses import dataclass
from typing import Optional

_TESTID = re.compile(r"getByTestId\(\s*['\"]([^'\"]+)['\"]")
_ROLE = re.compile(r"getByRole\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*\{[^}]*?name:\s*['\"]([^'\"]+)['\"])?")
_TEXT = re.compile(r"getByText\(\s*['\"]([^'\"]+)['\"]")
_CSS = re.compile(r"locator\(\s*['\"]([^'\"]+)['\"]")


@dataclass(frozen=True)
class BrokenSelector:
    kind: str            # css | testid | text | role
    value: str
    name: Optional[str] = None


def _match(text: str) -> Optional[BrokenSelector]:
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


def parse_broken_selector(error_message: str, trace: Optional[str] = None) -> Optional[BrokenSelector]:
    """Extrae el locator roto del error de Playwright. Busca PRIMERO en el mensaje de
    error (el locator que realmente falló) y solo si no halla nada recurre al trace,
    para no capturar un locator de un paso anterior del test.
    Soporta getByTestId/getByRole/getByText/locator(css). None si no reconoce nada."""
    return _match(error_message or "") or _match(trace or "")
