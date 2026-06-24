from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.actions.selfheal.dom import ElementSignature, _implicit_role, _norm_text
from src.actions.selfheal.locator import robust_locator


@dataclass
class ScoredCandidate:
    locator: str
    score: int
    why: str


def find_candidates(soup: BeautifulSoup, sig: ElementSignature) -> List[Tag]:
    """Elementos del DOM rojo compatibles con la firma (por testid/aria/texto/role/tag)."""
    seen = set()
    out: List[Tag] = []

    def add(el):
        if isinstance(el, Tag) and id(el) not in seen:
            seen.add(id(el))
            out.append(el)

    if sig.testid:
        for el in soup.find_all(attrs={"data-testid": sig.testid}):
            add(el)
    if sig.aria_label:
        for el in soup.find_all(attrs={"aria-label": sig.aria_label}):
            add(el)
    if sig.text:
        for node in soup.find_all(string=lambda s: s and sig.text in _norm_text(s)):
            add(node.parent)
    if sig.role:
        for el in soup.find_all(attrs={"role": sig.role}):
            add(el)
    for el in soup.find_all(sig.tag):
        add(el)
    return out


def _score(el: Tag, sig: ElementSignature) -> int:
    s = 0
    if sig.testid and el.get("data-testid") == sig.testid:
        s += 50
    if sig.aria_label and el.get("aria-label") == sig.aria_label:
        s += 30
    cand_text = _norm_text(el.get_text())
    if sig.text and cand_text == sig.text:
        s += 40
    elif sig.text and cand_text and sig.text in cand_text:
        s += 15
    if sig.role and (el.get("role") or _implicit_role(el.name)) == sig.role:
        s += 20
    if el.name == sig.tag:
        s += 10
    return s + robust_locator(el)[1]


def _why(el: Tag, sig: ElementSignature) -> str:
    bits = []
    cand_text = _norm_text(el.get_text())
    if sig.text and cand_text == sig.text:
        bits.append("texto")
    elif sig.text and cand_text and sig.text in cand_text:
        bits.append("texto parcial")
    if sig.role and (el.get("role") or _implicit_role(el.name)) == sig.role:
        bits.append("role")
    if sig.testid and el.get("data-testid") == sig.testid:
        bits.append("testid")
    if sig.aria_label and el.get("aria-label") == sig.aria_label:
        bits.append("aria-label")
    return ", ".join(bits) or "coincidencia parcial"


def rank(candidates: List[Tag], sig: ElementSignature) -> List[ScoredCandidate]:
    scored = [
        (ScoredCandidate(locator=robust_locator(el)[0], score=_score(el, sig), why=_why(el, sig)))
        for el in candidates
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
