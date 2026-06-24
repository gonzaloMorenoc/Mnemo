from typing import Tuple

from bs4.element import Tag

from src.actions.selfheal.dom import _implicit_role, _norm_text


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def robust_locator(el: Tag) -> Tuple[str, int]:
    """Mejor locator Playwright/TS por prioridad de robustez:
    getByRole(4) > getByTestId(3) > getByText(2) > #id(1) > css tag(0)."""
    role = el.get("role") or _implicit_role(el.name)
    text = _norm_text(el.get_text())
    testid = el.get("data-testid")
    aria = el.get("aria-label")
    el_id = el.get("id")
    name = aria or text
    if role and name:
        return (f"getByRole('{_esc(role)}', {{ name: '{_esc(name)}' }})", 4)
    if testid:
        return (f"getByTestId('{_esc(testid)}')", 3)
    if text:
        # exact:true porque getByText hace substring match por defecto en Playwright
        # (sin exact, 'Save' resolvería también a 'Save draft' → strict-mode violation).
        return (f"getByText('{_esc(text)}', {{ exact: true }})", 2)
    if el_id:
        return (f"locator('#{_esc(el_id)}')", 1)
    return (f"locator('{_esc(el.name)}')", 0)
