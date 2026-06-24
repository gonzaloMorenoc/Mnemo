from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.actions.selfheal.selector import BrokenSelector

_IMPLICIT_ROLE = {
    "button": "button", "a": "link", "select": "combobox", "textarea": "textbox",
    "img": "img", "h1": "heading", "h2": "heading", "h3": "heading",
    "h4": "heading", "h5": "heading", "h6": "heading",
}


def _norm_text(s: Optional[str]) -> str:
    return " ".join((s or "").split())


def _implicit_role(tag: str) -> Optional[str]:
    if tag == "input":
        return "textbox"
    return _IMPLICIT_ROLE.get(tag)


@dataclass(frozen=True)
class ElementSignature:
    tag: str
    role: Optional[str]
    text: str
    testid: Optional[str]
    aria_label: Optional[str]
    el_id: Optional[str]


def find_element(soup: BeautifulSoup, broken: BrokenSelector) -> Optional[Tag]:
    """Aplica el selector roto al DOM verde para hallar el elemento viejo. None si no casa."""
    try:
        if broken.kind == "css":
            return soup.select_one(broken.value)
        if broken.kind == "testid":
            return soup.find(attrs={"data-testid": broken.value})
        if broken.kind == "text":
            node = soup.find(string=lambda s: s and _norm_text(s) == broken.value)
            return node.parent if node else None
        if broken.kind == "role":
            for el in soup.find_all(True):
                role = el.get("role") or _implicit_role(el.name)
                if role == broken.value and (
                    broken.name is None
                    or _norm_text(el.get_text()) == broken.name
                    or el.get("aria-label") == broken.name
                ):
                    return el
        return None
    except Exception:  # noqa: BLE001 — selector no soportado → degrade
        return None


def signature(el: Tag) -> ElementSignature:
    return ElementSignature(
        tag=el.name,
        role=el.get("role") or _implicit_role(el.name),
        text=_norm_text(el.get_text()),
        testid=el.get("data-testid"),
        aria_label=el.get("aria-label"),
        el_id=el.get("id"),
    )
