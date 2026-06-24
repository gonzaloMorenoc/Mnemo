# Mnemo Autopilot — F3b: self-heal del locator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Para un veredicto de mantenimiento, generar de forma determinista un **locator robusto** y el cambio propuesto, como `ActionProposal(kind="self_heal")` (estado `proposed`), parseando el DOM verde/rojo con BeautifulSoup4. El LLM solo refina la explicación (opcional, degradable).

**Architecture:** `src/actions/selfheal/` — `selector` (parsea el locator roto del error), `dom` (bs4: elemento viejo del DOM verde + firma), `locator` (genera el robusto por prioridad), `candidates` (busca+rankea en el DOM rojo), `explainer` (LLM opcional), `selfheal` (`SelfHealActuator` que orquesta y degrada a `None`). Repo `get_selfheal_context`. `ActionService` mapea `maintenance → SelfHealActuator`.

**Tech Stack:** Python 3.13, BeautifulSoup4 (nuevo), psycopg, pytest. Todo puro salvo el método de repo (integración).

## Global Constraints

- **Determinista manda, LLM opcional.** El parseo/búsqueda/ranking/generación de locator son deterministas y testeables sin LLM. El `explainer` (LLM) es opcional y degradable: si es `None` o lanza → **explicación por plantilla** (la plantilla vive en el actuador).
- **Degrada a `None`** (→ `skipped` en `ActionService`) en cualquier paso sin datos (sin DOM, selector no parseable, elemento viejo no hallado, sin candidatos). **Nunca lanza** desde `propose`.
- **Nivel 2 intacto:** el self-heal solo **propone**; nada se materializa sin `approve` (F3a). `NullCodeHost` no escribe nada.
- Prioridad de robustez del locator: `getByRole` (4) > `getByTestId` (3) > `getByText` (2) > `#id` (1) > CSS tag (0).
- Orden de dependencias entre módulos: `dom` → `locator` → `candidates` → `selfheal`. `selector` y `explainer` son independientes.
- bs4 se usa con el backend `"html.parser"` (stdlib, sin dependencia de C). typing.Optional/List/Dict/Tuple. Tests del repo = `integration`. Commit `<type>: <description>`.

---

### Task 1: `bs4` + `src/actions/selfheal/selector.py` — `parse_broken_selector`

**Files:**
- Modify: `requirements.txt` (añadir `beautifulsoup4`)
- Create: `src/actions/selfheal/__init__.py` (vacío)
- Create: `src/actions/selfheal/selector.py`
- Test: `tests/test_selfheal_selector.py`

**Interfaces:**
- Produces: `BrokenSelector(kind, value, name=None)` (dataclass; `kind` ∈ `css|testid|text|role`); `parse_broken_selector(error_message: str, trace: Optional[str]=None) -> Optional[BrokenSelector]`.

- [ ] **Step 1: Añadir bs4** a `requirements.txt` (una línea, p. ej. `beautifulsoup4>=4.12`) y `pip install beautifulsoup4`.

Run: `python3 -c "import bs4; print(bs4.__version__)"`
Expected: imprime una versión (>=4.12).

- [ ] **Step 2: Escribir los tests**

```python
# tests/test_selfheal_selector.py
from src.actions.selfheal.selector import BrokenSelector, parse_broken_selector


def test_parse_css():
    b = parse_broken_selector("waiting for locator('#checkout-btn')")
    assert b == BrokenSelector(kind="css", value="#checkout-btn")


def test_parse_testid():
    b = parse_broken_selector("Timeout waiting for getByTestId('checkout')")
    assert b.kind == "testid" and b.value == "checkout"


def test_parse_text():
    b = parse_broken_selector("waiting for getByText('Checkout')")
    assert b.kind == "text" and b.value == "Checkout"


def test_parse_role_with_name():
    b = parse_broken_selector("waiting for getByRole('button', { name: 'Checkout' })")
    assert b.kind == "role" and b.value == "button" and b.name == "Checkout"


def test_parse_searches_trace_too():
    b = parse_broken_selector("Timeout", trace="...\n  at locator('.submit')\n...")
    assert b.kind == "css" and b.value == ".submit"


def test_parse_none_when_unrecognized():
    assert parse_broken_selector("some unrelated error", trace=None) is None
```

- [ ] **Step 3: Implementar**

```python
# src/actions/selfheal/__init__.py  (vacío)
```
```python
# src/actions/selfheal/selector.py
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
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_selfheal_selector.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/actions/selfheal/__init__.py src/actions/selfheal/selector.py tests/test_selfheal_selector.py
git commit -m "feat(selfheal): bs4 + parse_broken_selector (locator roto del error)"
```

---

### Task 2: `src/actions/selfheal/dom.py` — `find_element` + `signature` (bs4)

**Files:**
- Create: `src/actions/selfheal/dom.py`
- Test: `tests/test_selfheal_dom.py`

**Interfaces:**
- Consumes: `BrokenSelector` (Task 1); `bs4.BeautifulSoup`/`Tag`.
- Produces: `_norm_text(s) -> str`; `_implicit_role(tag) -> Optional[str]`; `ElementSignature(tag, role, text, testid, aria_label, el_id)`; `find_element(soup, broken) -> Optional[Tag]`; `signature(el) -> ElementSignature`.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_selfheal_dom.py
from bs4 import BeautifulSoup

from src.actions.selfheal.dom import find_element, signature
from src.actions.selfheal.selector import BrokenSelector

_GREEN = """
<html><body>
  <button id="checkout-btn" data-testid="checkout" aria-label="Checkout now">Checkout</button>
  <a href="/x">Home</a>
</body></html>
"""


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def test_find_element_by_css_id():
    el = find_element(_soup(_GREEN), BrokenSelector("css", "#checkout-btn"))
    assert el is not None and el.name == "button"


def test_find_element_by_testid():
    el = find_element(_soup(_GREEN), BrokenSelector("testid", "checkout"))
    assert el is not None and el.get("id") == "checkout-btn"


def test_find_element_by_text():
    el = find_element(_soup(_GREEN), BrokenSelector("text", "Checkout"))
    assert el is not None and el.name == "button"


def test_find_element_none_when_absent():
    assert find_element(_soup(_GREEN), BrokenSelector("css", "#nope")) is None


def test_signature_extracts_stable_attrs():
    el = find_element(_soup(_GREEN), BrokenSelector("css", "#checkout-btn"))
    sig = signature(el)
    assert sig.tag == "button" and sig.role == "button"
    assert sig.text == "Checkout" and sig.testid == "checkout"
    assert sig.aria_label == "Checkout now" and sig.el_id == "checkout-btn"
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_selfheal_dom.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
# src/actions/selfheal/dom.py
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


@dataclass
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
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_selfheal_dom.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/selfheal/dom.py tests/test_selfheal_dom.py
git commit -m "feat(selfheal): find_element + signature (bs4)"
```

---

### Task 3: `src/actions/selfheal/locator.py` — `robust_locator`

**Files:**
- Create: `src/actions/selfheal/locator.py`
- Test: `tests/test_selfheal_locator.py`

**Interfaces:**
- Consumes: `_implicit_role`/`_norm_text` (Task 2); `bs4` `Tag`.
- Produces: `robust_locator(el: Tag) -> Tuple[str, int]` — `(locator_playwright, rank)` con rank de robustez (4..0). `_esc(s) -> str`.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_selfheal_locator.py
from bs4 import BeautifulSoup

from src.actions.selfheal.locator import robust_locator


def _el(html):
    return BeautifulSoup(html, "html.parser").find(True)


def test_role_with_name_is_best():
    loc, rank = robust_locator(_el("<button>Checkout</button>"))
    assert loc == "getByRole('button', { name: 'Checkout' })" and rank == 4


def test_testid_when_no_accessible_name():
    loc, rank = robust_locator(_el("<div data-testid='cart'></div>"))
    assert loc == "getByTestId('cart')" and rank == 3


def test_text_when_no_role_no_testid():
    loc, rank = robust_locator(_el("<span>Total</span>"))
    assert loc == "getByText('Total')" and rank == 2


def test_id_fallback():
    loc, rank = robust_locator(_el("<div id='x'></div>"))
    assert loc == "locator('#x')" and rank == 1


def test_css_tag_last_resort():
    loc, rank = robust_locator(_el("<section></section>"))
    assert rank == 0 and "section" in loc


def test_escapes_single_quotes():
    loc, _ = robust_locator(_el("<button>It's go</button>"))
    assert "\\'" in loc
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_selfheal_locator.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
# src/actions/selfheal/locator.py
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
        return (f"getByText('{_esc(text)}')", 2)
    if el_id:
        return (f"locator('#{_esc(el_id)}')", 1)
    return (f"locator('{_esc(el.name)}')", 0)
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_selfheal_locator.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/selfheal/locator.py tests/test_selfheal_locator.py
git commit -m "feat(selfheal): robust_locator (prioridad de robustez)"
```

---

### Task 4: `src/actions/selfheal/candidates.py` — `find_candidates` + `rank`

**Files:**
- Create: `src/actions/selfheal/candidates.py`
- Test: `tests/test_selfheal_candidates.py`

**Interfaces:**
- Consumes: `ElementSignature`/`_implicit_role`/`_norm_text` (Task 2), `robust_locator` (Task 3), `bs4`.
- Produces: `ScoredCandidate(locator, score, why)`; `find_candidates(soup, sig) -> List[Tag]`; `rank(candidates, sig) -> List[ScoredCandidate]` (orden desc por score).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_selfheal_candidates.py
from bs4 import BeautifulSoup

from src.actions.selfheal.candidates import find_candidates, rank
from src.actions.selfheal.dom import ElementSignature

_FAILURE = """
<html><body>
  <button id="checkout-button-v2">Checkout</button>
  <button id="cancel">Cancel</button>
</body></html>
"""


def _sig():
    return ElementSignature(tag="button", role="button", text="Checkout",
                            testid=None, aria_label=None, el_id="checkout-btn")


def test_finds_renamed_element():
    soup = BeautifulSoup(_FAILURE, "html.parser")
    cands = find_candidates(soup, _sig())
    assert any(c.get_text(strip=True) == "Checkout" for c in cands)


def test_ranks_semantic_match_first():
    soup = BeautifulSoup(_FAILURE, "html.parser")
    ranked = rank(find_candidates(soup, _sig()), _sig())
    assert ranked[0].locator == "getByRole('button', { name: 'Checkout' })"
    assert ranked[0].score > ranked[1].score          # Checkout supera a Cancel
    assert "texto" in ranked[0].why or "role" in ranked[0].why


def test_rank_empty_when_no_candidates():
    soup = BeautifulSoup("<html><body><p>nada</p></body></html>", "html.parser")
    assert rank(find_candidates(soup, _sig()), _sig()) == []
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_selfheal_candidates.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
# src/actions/selfheal/candidates.py
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
    if sig.text and _norm_text(el.get_text()) == sig.text:
        bits.append("mismo texto")
    if sig.role and (el.get("role") or _implicit_role(el.name)) == sig.role:
        bits.append("mismo role")
    if sig.testid and el.get("data-testid") == sig.testid:
        bits.append("mismo testid")
    if sig.aria_label and el.get("aria-label") == sig.aria_label:
        bits.append("misma aria-label")
    return ", ".join(bits) or "coincidencia parcial"


def rank(candidates: List[Tag], sig: ElementSignature) -> List[ScoredCandidate]:
    scored = [
        (ScoredCandidate(locator=robust_locator(el)[0], score=_score(el, sig), why=_why(el, sig)))
        for el in candidates
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_selfheal_candidates.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/selfheal/candidates.py tests/test_selfheal_candidates.py
git commit -m "feat(selfheal): find_candidates + rank (similitud + robustez)"
```

---

### Task 5: `explainer.py` + `selfheal.py` — `SelfHealActuator`

**Files:**
- Create: `src/actions/selfheal/explainer.py`
- Create: `src/actions/selfheal/selfheal.py`
- Test: `tests/test_selfheal_actuator.py`

**Interfaces:**
- Consumes: `parse_broken_selector` (T1), `find_element`/`signature` (T2), `find_candidates`/`rank` (T4), `ActionProposal` (F3a `src/actions/base.py`), `LLMProvider`/`strip_reasoning`.
- Produces: `SelfHealExplainer` (Protocol) + `LLMSelfHealExplainer(provider)`; `SelfHealActuator(explainer=None)` con `propose(verdict, context) -> Optional[ActionProposal]`.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_selfheal_actuator.py
from unittest.mock import MagicMock

from src.actions.selfheal.selfheal import SelfHealActuator

_GREEN = "<button id='checkout-btn'>Checkout</button>"
_FAILURE = "<button id='checkout-v2'>Checkout</button><button id='c'>Cancel</button>"


def _ctx(**over):
    base = {"error_message": "waiting for locator('#checkout-btn')", "trace": None,
            "green_dom": _GREEN, "failure_dom": _FAILURE}
    base.update(over)
    return base


def test_e2e_renamed_id_to_getbyrole():
    p = SelfHealActuator().propose({"category": "maintenance"}, _ctx())
    assert p is not None and p.kind == "self_heal"
    assert p.payload["suggested_locator"] == "getByRole('button', { name: 'Checkout' })"
    assert "checkout-btn" in p.payload["broken_locator"]
    assert p.payload["candidates"] and "robusto" in p.payload["reasoning"].lower()


def test_degrades_no_dom():
    assert SelfHealActuator().propose({}, _ctx(green_dom=None, failure_dom=None)) is None


def test_degrades_unparseable_selector():
    assert SelfHealActuator().propose({}, _ctx(error_message="boom genérico")) is None


def test_degrades_old_element_not_in_green():
    assert SelfHealActuator().propose({}, _ctx(error_message="locator('#missing')")) is None


def test_uses_explainer_when_present():
    explainer = MagicMock()
    explainer.explain.return_value = "Razón del LLM."
    p = SelfHealActuator(explainer=explainer).propose({}, _ctx())
    assert p.payload["reasoning"] == "Razón del LLM."


def test_degrades_explainer_raises_to_template():
    explainer = MagicMock()
    explainer.explain.side_effect = RuntimeError("LLM caído")
    p = SelfHealActuator(explainer=explainer).propose({}, _ctx())
    assert "robusto" in p.payload["reasoning"].lower()
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_selfheal_actuator.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
# src/actions/selfheal/explainer.py
from typing import Any, Dict, List, Protocol

from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning


class SelfHealExplainer(Protocol):
    def explain(
        self, *, broken_locator: str, suggested_locator: str, candidates: List[Dict[str, Any]]
    ) -> str: ...


def _build_prompt(broken_locator: str, suggested_locator: str, candidates: List[Dict[str, Any]]) -> str:
    alts = "\n".join(f"- {c['locator']} (score {c['score']}, {c['why']})" for c in candidates[:5])
    return (
        "Eres un ingeniero de QA. Un locator de Playwright dejó de resolver porque el DOM cambió. "
        "Explica en 1-2 frases por qué el locator sugerido es más robusto que el roto. "
        "Básate SOLO en los datos, no inventes.\n\n"
        f"Locator roto: {broken_locator}\n"
        f"Locator sugerido: {suggested_locator}\n"
        f"Candidatos:\n{alts}\n"
    )


class LLMSelfHealExplainer:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def explain(self, *, broken_locator: str, suggested_locator: str, candidates) -> str:
        return strip_reasoning(
            self._provider.complete(_build_prompt(broken_locator, suggested_locator, candidates))
        )
```
```python
# src/actions/selfheal/selfheal.py
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

from src.actions.base import ActionProposal
from src.actions.selfheal.candidates import find_candidates, rank
from src.actions.selfheal.dom import find_element, signature
from src.actions.selfheal.selector import BrokenSelector, parse_broken_selector

_TOP_N = 3


def _broken_str(b: BrokenSelector) -> str:
    if b.kind == "role":
        return f"getByRole('{b.value}'" + (f", name='{b.name}')" if b.name else ")")
    if b.kind == "testid":
        return f"getByTestId('{b.value}')"
    if b.kind == "text":
        return f"getByText('{b.value}')"
    return f"locator('{b.value}')"


class SelfHealActuator:
    """maintenance → locator robusto (determinista). El explainer (LLM) es opcional y
    degradable. Devuelve None (→ skipped) si no puede curar; NUNCA lanza."""

    def __init__(self, explainer: Optional[Any] = None):
        self._explainer = explainer

    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]:
        try:
            broken = parse_broken_selector(context.get("error_message") or "", context.get("trace"))
            green, failure = context.get("green_dom"), context.get("failure_dom")
            if broken is None or not green or not failure:
                return None
            old_el = find_element(BeautifulSoup(green, "html.parser"), broken)
            if old_el is None:
                return None
            sig = signature(old_el)
            ranked = rank(find_candidates(BeautifulSoup(failure, "html.parser"), sig), sig)
            if not ranked:
                return None
            top = ranked[0]
            broken_str = _broken_str(broken)
            cands = [{"locator": c.locator, "score": c.score, "why": c.why} for c in ranked[:_TOP_N]]
            reasoning = self._reasoning(broken_str, top.locator, cands)
            return ActionProposal(
                kind="self_heal",
                payload={"broken_locator": broken_str, "suggested_locator": top.locator,
                         "candidates": cands, "reasoning": reasoning},
                summary=f"Self-heal: {broken_str} → {top.locator}",
            )
        except Exception:  # noqa: BLE001 — el self-heal nunca rompe propose_actions
            return None

    def _reasoning(self, broken_str: str, suggested: str, candidates) -> str:
        template = (
            f"El locator `{broken_str}` dejó de resolver tras el cambio de DOM; `{suggested}` "
            "apunta al mismo elemento por semántica estable (role/nombre/testid), más robusto."
        )
        if self._explainer is None:
            return template
        try:
            return self._explainer.explain(
                broken_locator=broken_str, suggested_locator=suggested, candidates=candidates
            )
        except Exception:  # noqa: BLE001 — LLM degrada a plantilla
            return template
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_selfheal_actuator.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/selfheal/explainer.py src/actions/selfheal/selfheal.py tests/test_selfheal_actuator.py
git commit -m "feat(selfheal): SelfHealActuator + explainer LLM opcional (degrada)"
```

---

### Task 6: Repo `get_selfheal_context` + wiring en `ActionService`/`get_action_service`

**Files:**
- Modify: `src/defects/repository.py` (`get_selfheal_context`)
- Modify: `src/actions/service.py` (`_context_for`: rama `maintenance`)
- Modify: `src/api_v2.py` (`get_action_service`: actuador `maintenance` + `_LazySelfHealExplainer`)
- Test: `tests/test_actions_repository.py` (añadir, integration) y `tests/test_actions_service.py` (añadir)

**Interfaces:**
- Consumes: `SelfHealActuator`/`LLMSelfHealExplainer` (T5), `get_llm_provider`.
- Produces: `get_selfheal_context(*, user_id, failure_id) -> Optional[Dict]` (`{error_message, trace, green_dom, failure_dom}`); `ActionService._context_for` rama maintenance; `get_action_service` registra `"maintenance": SelfHealActuator(...)`.

- [ ] **Step 1: Escribir los tests**

En `tests/test_actions_repository.py` (integration) añadir:
```python
def test_get_selfheal_context_returns_error_and_doms(repo, org):
    u, o = org["user_id"], org["org_id"]
    from src.defects.fingerprint import fingerprint
    from src.defects.repository import IngestItem
    from src.ingest.models import FailureRecord
    rec = FailureRecord(test_name="t_co", error_type="TimeoutError",
                        message="waiting for locator('#btn')", trace=None, project="web", source="playwright")
    item = IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=[1.0] + [0.0] * 383)
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="web", source="playwright", run_uid="sh",
                           commit_sha="c1", items=[item],
                           results=[{"test_name": "t_co", "status": "fail"}],
                           snapshots=[{"test_name": "t_co", "kind": "last_green", "content": "<button>Go</button>", "commit_sha": "c0"},
                                      {"test_name": "t_co", "kind": "failure", "content": "<button id='v2'>Go</button>", "commit_sha": "c1"}])
    fid = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["failure_id"]
    ctx = repo.get_selfheal_context(user_id=u, failure_id=fid)
    assert ctx is not None
    assert "locator('#btn')" in ctx["error_message"]
    assert ctx["green_dom"] == "<button>Go</button>" and "v2" in ctx["failure_dom"]
    import uuid as _uuid
    assert repo.get_selfheal_context(user_id=str(_uuid.uuid4()), failure_id=fid) is None
```
En `tests/test_actions_service.py` añadir (mockeado):
```python
def test_maintenance_uses_selfheal_context():
    from unittest.mock import MagicMock
    from src.actions.base import ActionProposal
    repo = MagicMock()
    repo.get_run_actionable_verdicts.return_value = [
        {"verdict_id": "v1", "category": "maintenance", "org_id": "o", "evidence_bundle": {},
         "test_name": "t", "failure_id": "f1"}]
    repo.get_selfheal_context.return_value = {"error_message": "e", "trace": None,
                                              "green_dom": "<a/>", "failure_dom": "<a/>"}
    repo.save_actions.return_value = 1
    sh = MagicMock()
    sh.propose.return_value = ActionProposal("self_heal", {"suggested_locator": "x"}, "s")
    svc = ActionService(repo=repo, actuators={"maintenance": sh})
    counts = svc.propose_actions(user_id="u", run_id="r")
    repo.get_selfheal_context.assert_called_once_with(user_id="u", failure_id="f1")
    _, ctx = sh.propose.call_args.args
    assert ctx["green_dom"] == "<a/>" and ctx["error_message"] == "e"
    assert counts.get("self_heal", 0) == 1 or counts == {"quarantine": 0, "ticket": 0, "self_heal": 1, "skipped": 0}
```
(Nota: `ProposeActionsResponse`/`counts` no tiene campo `self_heal` hoy; en este Step añade `self_heal` al dict de `counts` del servicio — ver Step 3 — y, si el endpoint lo serializa, amplía `ProposeActionsResponse` con `self_heal: int = 0` en `src/multitenant_models.py`.)

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_actions_repository.py -v -k selfheal && pytest tests/test_actions_service.py -v -k maintenance`
Expected: FAIL — `get_selfheal_context` no existe / rama maintenance no arma el context.

- [ ] **Step 3: Implementar**

(a) `src/defects/repository.py` — añadir al final de `AssuranceRepository`:
```python
    def get_selfheal_context(self, *, user_id: str, failure_id: str) -> Optional[Dict[str, Any]]:
        """Contexto para el self-heal de un fallo: el error + los DOM verde/rojo del test.
        None si no es miembro / no existe el fallo."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select f.message, f.trace, f.test_name, r.org_id, r.project, r.commit_sha"
                    " from public.failures f join public.test_runs r on r.id = f.run_id"
                    " where f.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (failure_id, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    "select content from public.dom_snapshots"
                    " where org_id = %s and project = %s and test_name = %s and kind = 'last_green'"
                    " order by created_at desc limit 1",
                    (row["org_id"], row["project"], row["test_name"]),
                )
                green = cur.fetchone()
                cur.execute(
                    "select content from public.dom_snapshots"
                    " where org_id = %s and project = %s and test_name = %s and kind = 'failure'"
                    "   and commit_sha is not distinct from %s order by created_at desc limit 1",
                    (row["org_id"], row["project"], row["test_name"], row["commit_sha"]),
                )
                fail = cur.fetchone()
        return {
            "error_message": row["message"], "trace": row["trace"],
            "green_dom": green["content"] if green else None,
            "failure_dom": fail["content"] if fail else None,
        }
```

(b) `src/actions/service.py` — en `_context_for`, añadir la rama `maintenance` y `self_heal` en los counts. Cambiar `_CATEGORIES` para incluir `self_heal`, y `_context_for`:
```python
_CATEGORIES = ("quarantine", "ticket", "self_heal")
```
```python
    def _context_for(self, user_id: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"test_name": verdict.get("test_name")}
        category = verdict["category"]
        if category == "real" and verdict.get("defect_family_id"):
            fam = self.repo.get_family_with_failures(
                user_id=user_id, defect_id=verdict["defect_family_id"]
            )
            if fam:
                ctx["family"] = fam.get("family") or {}
                ctx["failures"] = fam.get("failures") or []
        elif category == "maintenance" and verdict.get("failure_id"):
            sh = self.repo.get_selfheal_context(user_id=user_id, failure_id=verdict["failure_id"])
            if sh:
                ctx.update(sh)
        return ctx
```

(c) `src/api_v2.py` — añadir el explainer perezoso y registrar el actuador maintenance:
```python
from src.actions.selfheal.selfheal import SelfHealActuator


class _LazySelfHealExplainer:
    """Construye el explainer LLM en tiempo de uso (mala config del LLM → degrada a plantilla)."""

    def explain(self, **kw):
        from src.actions.selfheal.explainer import LLMSelfHealExplainer
        return LLMSelfHealExplainer(get_llm_provider()).explain(**kw)
```
En `get_action_service`, ampliar el dict de actuadores:
```python
            actuators={
                "flaky": QuarantineActuator(),
                "real": TicketActuator(_LazyRootCauseAnalyzer()),
                "maintenance": SelfHealActuator(explainer=_LazySelfHealExplainer()),
            },
```
(Si `ProposeActionsResponse` se valida estrictamente, añadir `self_heal: int = 0` en `src/multitenant_models.py`.)

- [ ] **Step 4: Ejecutar (pasa) + suite completa**

Run: `pytest tests/test_actions_repository.py tests/test_actions_service.py tests/test_api_v2_actions.py -v && pytest -m "not integration" -q`
Expected: integración + servicio + endpoints PASS; suite unitaria completa verde (sin regresiones; ojo a los tests de `propose_actions` que asertan el dict de counts — actualizar al nuevo `self_heal`).

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py src/actions/service.py src/api_v2.py src/multitenant_models.py tests/test_actions_repository.py tests/test_actions_service.py
git commit -m "feat(selfheal): get_selfheal_context + wiring maintenance→SelfHealActuator"
```

---

## Self-Review

**1. Cobertura del spec (F3b):**
- `selector.py` (parse del locator roto, 4 formas) → Task 1. ✓
- `dom.py` (find_element por forma + signature, bs4) → Task 2. ✓
- `locator.py` (robust_locator por prioridad) → Task 3. ✓
- `candidates.py` (find_candidates + rank por similitud+robustez) → Task 4. ✓
- `explainer.py` (LLM opcional, propio — NO root-cause) + `selfheal.py` (`SelfHealActuator`, degrada a None) → Task 5. ✓
- Repo `get_selfheal_context` + `ActionService` maintenance→SelfHeal + registro → Task 6. ✓
- bs4 (html.parser) añadido → Task 1. ✓

**2. Placeholders:** ninguno; código/SQL completo + comandos con salida esperada.

**3. Consistencia de tipos:** `BrokenSelector` (T1) lo consumen `find_element` (T2) y `_broken_str` (T5); `ElementSignature` (T2) lo consumen `find_candidates`/`_score` (T4) y `signature` (T2); `robust_locator -> (str,int)` (T3) lo usan `rank` (T4) y los tests; `ScoredCandidate` (T4) → el `payload.candidates` del actuador (T5); `SelfHealActuator.propose(verdict, context)` (T5) lo invoca `ActionService` (T6, F3a) con el context de `get_selfheal_context` (T6); `ActionProposal(kind="self_heal")` encaja con el CHECK de la migración 010 (F3a) y con el branch `None→skipped` (F3a). El nuevo conteo `self_heal` se añade a `_CATEGORIES`/`ProposeActionsResponse`.

**Nota:** `repository.py` sigue creciendo (>800 líneas; F3b añade 1 método). La extracción de `ActionRepository`/`TriageRepository` queda para cuando se aborde F3c (ya anotado).

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-24-mnemo-autopilot-f3b-selfheal.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> Rama `feat/mnemo-selfheal` (apilada sobre `feat/mnemo-actions`/F3a). Tasks 1-5 son puras (bs4, sin BD/LLM/GitHub — el LLM se mockea); Task 6 toca la BD (integration) + el wiring. Tras F3b: **F3c** (GitHub App: PR borrador real con el diff del locator + resolución de file:line vía grep del repo).
