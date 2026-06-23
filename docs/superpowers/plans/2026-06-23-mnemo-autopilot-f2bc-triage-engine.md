# Mnemo Autopilot — F2b/F2c: motor de triaje puro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el **motor de triaje determinista puro** — clasifica un fallo en *flaky / infra / mantenimiento / defecto real / unknown(ambiguo)* a partir de señales objetivas, con confianza calibrada y un `evidence_bundle` auditable — todo en funciones puras testeables sin BD ni LLM.

**Architecture:** Cuatro módulos puros en `src/triage/`: `patterns` (clasifica el mensaje de error), `signals` (ensambla las señales objetivas a partir de hechos ya recuperados), `engine` (reglas de prioridad → veredicto), `evidence` (bundle auditable). Los hechos que dependen de BD (intermitencia, DOM cambiado, etc.) se reciben como entradas ya recuperadas; la capa de repositorio que los obtiene es F2d. El desempate LLM de los ambiguos es F2f.

**Tech Stack:** Python 3.13, dataclasses, `re`, pytest. Sin dependencias de BD/LLM.

## Global Constraints

- Módulos **puros** en `src/triage/` (sin I/O, sin BD, sin LLM). Funciones puras + dataclasses; archivos pequeños y enfocados.
- **Reglas y confianzas exactas (spec F2 §3.2):** flaky `0.90`, infra `0.90`, mantenimiento `0.80`, defecto real recurrente `0.85`, defecto real novedoso `0.75`. `requires_approval = confianza < 0.80 OR (category=='real' AND novel) OR llm_assisted`. En F2c `llm_assisted=False` (el LLM es F2f). Ambiguo (R6) → `category='unknown'`, `confidence=0.0`, `ambiguous=True`, `requires_approval=True`.
- **`TriageVerdict`** (spec §5): `category, confidence, rule_applied, requires_approval, llm_assisted, ambiguous`.
- **`Signals`** = las señales de §3.1. La función pura recibe los hechos de BD ya recuperados (`FailureInput`); NO consulta BD.
- Sin sintaxis que rompa <3.10 en módulos compartidos: usar `typing.Optional/List/Dict/Set`, no PEP 604 (`X | None`) — coherente con el resto del repo.
- TDD table-driven; tests sin BD/LLM (corren bajo `pytest -m "not integration"`). Commit: `<type>: <description>`.

---

### Task 1: `patterns.py` — clasificación del error (infra / locator / assertion)

**Files:**
- Create: `src/triage/__init__.py` (vacío)
- Create: `src/triage/patterns.py`
- Test: `tests/test_triage_patterns.py`

**Interfaces:**
- Produces: `classify_error(error_type: Optional[str], message: str) -> Set[str]` — subconjunto de `{"infra","locator","assertion"}` (no excluyente).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_triage_patterns.py
from src.triage.patterns import classify_error


def test_infra_patterns():
    assert "infra" in classify_error("Error", "connect ECONNREFUSED 127.0.0.1:5432")
    assert "infra" in classify_error(None, "net::ERR_CONNECTION_RESET")
    assert "infra" in classify_error(None, "Target page, context or browser has been closed")


def test_locator_patterns():
    assert "locator" in classify_error("TimeoutError", "Timeout 30000ms exceeded waiting for locator")
    assert "locator" in classify_error(None, "locator.click: strict mode violation")
    assert "locator" in classify_error(None, "element is not visible")


def test_assertion_patterns():
    assert "assertion" in classify_error(None, "expect(received).toBe(expected)")
    assert "assertion" in classify_error("AssertionError", "Expected: 5  Received: 4")


def test_no_match_returns_empty():
    assert classify_error(None, "algo salió mal sin patrón conocido") == set()


def test_multiple_categories():
    cats = classify_error("TimeoutError", "expect(locator).toBeVisible() failed waiting for locator")
    assert "locator" in cats and "assertion" in cats
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_patterns.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.patterns`.

- [ ] **Step 3: Implementar**

```python
# src/triage/__init__.py  (vacío)
```

```python
# src/triage/patterns.py
import re
from typing import Optional, Set

# Clasificación heurística del error. Categorías NO excluyentes: un mensaje puede
# casar varias; el motor (engine) resuelve la prioridad. Cap de longitud como
# defensa frente a mensajes enormes. Alternaciones lineales (sin backtracking).

_INFRA = re.compile(
    r"ECONNREFUSED|ECONNRESET|ETIMEDOUT|EAI_AGAIN|net::ERR|socket hang up|"
    r"getaddrinfo|connection refused|target[^\n]{0,80}closed|"
    r"browser has been closed|page crashed|browser[^\n]{0,40}crash",
    re.IGNORECASE,
)
_LOCATOR = re.compile(
    r"locator|waiting for selector|waiting for locator|strict mode violation|"
    r"not visible|element is not|resolved to 0 elements|no element|no node found",
    re.IGNORECASE,
)
_ASSERTION = re.compile(
    r"expect\(|assertionerror|\bexpected:|\breceived:",
    re.IGNORECASE,
)


def classify_error(error_type: Optional[str], message: str) -> Set[str]:
    """Clasifica un error en {'infra','locator','assertion'} (no excluyente),
    combinando error_type + message."""
    text = f"{error_type or ''} {message or ''}"[:5000]
    cats: Set[str] = set()
    if _INFRA.search(text):
        cats.add("infra")
    if _LOCATOR.search(text):
        cats.add("locator")
    if _ASSERTION.search(text):
        cats.add("assertion")
    return cats
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_patterns.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/triage/__init__.py src/triage/patterns.py tests/test_triage_patterns.py
git commit -m "feat(triage): clasificación de error infra/locator/assertion"
```

---

### Task 2: `signals.py` — `FailureInput` + `Signals` + `compute_signals`

**Files:**
- Create: `src/triage/signals.py`
- Test: `tests/test_triage_signals.py`

**Interfaces:**
- Consumes: `classify_error` (Task 1).
- Produces: `FailureInput` (dataclass de entradas ya recuperadas), `Signals` (dataclass de señales), `compute_signals(failure: FailureInput) -> Signals`.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_triage_signals.py
from src.triage.signals import FailureInput, compute_signals


def _fi(**over):
    base = dict(
        error_type="TimeoutError", message="waiting for locator",
        is_novel=True, family_label="unknown", retry_passed_in_run=False,
        intermittent_same_sha=False, mass_cofailure=False,
        has_green_baseline=False, dom_changed=False,
    )
    base.update(over)
    return FailureInput(**base)


def test_classification_signals_from_message():
    s = compute_signals(_fi(message="locator not found"))
    assert s.locator_error is True and s.infra_error is False and s.assertion_failure is False


def test_known_flaky_family_from_label():
    assert compute_signals(_fi(family_label="flaky")).known_flaky_family is True
    assert compute_signals(_fi(family_label="real")).known_flaky_family is False


def test_novel_and_recurrent_are_complementary():
    assert compute_signals(_fi(is_novel=True)).novel is True
    assert compute_signals(_fi(is_novel=True)).recurrent is False
    assert compute_signals(_fi(is_novel=False)).recurrent is True


def test_facts_passed_through():
    s = compute_signals(_fi(retry_passed_in_run=True, intermittent_same_sha=True,
                            mass_cofailure=True, has_green_baseline=True, dom_changed=True))
    assert s.retry_passed_in_run and s.intermittent_same_sha and s.mass_cofailure
    assert s.has_green_baseline and s.dom_changed
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_signals.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.signals`.

- [ ] **Step 3: Implementar**

```python
# src/triage/signals.py
from dataclasses import dataclass
from typing import Optional

from src.triage.patterns import classify_error


@dataclass
class FailureInput:
    """Entradas ya recuperadas para clasificar un fallo. Los hechos de BD
    (intermitencia, DOM cambiado, etc.) los provee la capa de repositorio (F2d);
    aquí la lógica es PURA."""
    error_type: Optional[str]
    message: str
    is_novel: bool                  # familia recién creada (occurrence_count == 1)
    family_label: str               # 'flaky'|'real'|'maintenance'|'infra'|'unknown'
    retry_passed_in_run: bool       # pasó al reintentar en el MISMO run
    intermittent_same_sha: bool     # mismo test+commit con mezcla pass+fail entre runs
    mass_cofailure: bool            # el run tiene >= umbral de fallos con firma de infra
    has_green_baseline: bool        # existe snapshot last_green del test
    dom_changed: bool               # DOM de fallo != last_green (normalizado)


@dataclass
class Signals:
    infra_error: bool
    locator_error: bool
    assertion_failure: bool
    retry_passed_in_run: bool
    intermittent_same_sha: bool
    known_flaky_family: bool
    mass_cofailure: bool
    has_green_baseline: bool
    dom_changed: bool
    novel: bool
    recurrent: bool


def compute_signals(failure: FailureInput) -> Signals:
    cats = classify_error(failure.error_type, failure.message)
    return Signals(
        infra_error="infra" in cats,
        locator_error="locator" in cats,
        assertion_failure="assertion" in cats,
        retry_passed_in_run=failure.retry_passed_in_run,
        intermittent_same_sha=failure.intermittent_same_sha,
        known_flaky_family=failure.family_label == "flaky",
        mass_cofailure=failure.mass_cofailure,
        has_green_baseline=failure.has_green_baseline,
        dom_changed=failure.dom_changed,
        novel=failure.is_novel,
        recurrent=not failure.is_novel,
    )
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_signals.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/triage/signals.py tests/test_triage_signals.py
git commit -m "feat(triage): FailureInput/Signals + compute_signals (puro)"
```

---

### Task 3: `engine.py` — `TriageVerdict` + `triage` (reglas R1–R6)

**Files:**
- Create: `src/triage/engine.py`
- Test: `tests/test_triage_engine.py`

**Interfaces:**
- Consumes: `Signals` (Task 2).
- Produces: `TriageVerdict` (dataclass: `category, confidence, rule_applied, requires_approval, llm_assisted, ambiguous`), `triage(signals: Signals) -> TriageVerdict`.

- [ ] **Step 1: Escribir los tests (table-driven, una regla por caso)**

```python
# tests/test_triage_engine.py
from src.triage.engine import triage
from src.triage.signals import Signals


def _sig(**over):
    base = dict(
        infra_error=False, locator_error=False, assertion_failure=False,
        retry_passed_in_run=False, intermittent_same_sha=False, known_flaky_family=False,
        mass_cofailure=False, has_green_baseline=False, dom_changed=False,
        novel=False, recurrent=False,
    )
    base.update(over)
    return Signals(**base)


def test_r1_flaky_by_retry():
    v = triage(_sig(retry_passed_in_run=True))
    assert v.category == "flaky" and v.confidence == 0.90 and v.rule_applied == "R1_flaky"
    assert v.requires_approval is False and v.ambiguous is False and v.llm_assisted is False


def test_r1_flaky_by_intermittency_or_known_family():
    assert triage(_sig(intermittent_same_sha=True)).category == "flaky"
    assert triage(_sig(known_flaky_family=True)).category == "flaky"


def test_r2_infra_requires_mass_cofailure_and_infra_error():
    assert triage(_sig(mass_cofailure=True, infra_error=True)).category == "infra"
    assert triage(_sig(infra_error=True)).category != "infra"  # infra solo, sin co-fallo masivo


def test_r3_maintenance_requires_locator_baseline_dom_changed():
    v = triage(_sig(locator_error=True, has_green_baseline=True, dom_changed=True))
    assert v.category == "maintenance" and v.confidence == 0.80 and v.rule_applied == "R3_maintenance"
    assert v.requires_approval is False  # 0.80 NO es < 0.80
    # sin dom_changed → no es mantenimiento → ambiguo
    assert triage(_sig(locator_error=True, has_green_baseline=True)).category == "unknown"


def test_r4_real_recurrent():
    v = triage(_sig(assertion_failure=True, recurrent=True))
    assert v.category == "real" and v.confidence == 0.85 and v.requires_approval is False


def test_r5_real_novel_requires_approval():
    v = triage(_sig(assertion_failure=True, novel=True))
    assert v.category == "real" and v.confidence == 0.75 and v.requires_approval is True


def test_r6_ambiguous_unknown():
    v = triage(_sig(locator_error=True))  # locator sin baseline/dom_changed
    assert v.category == "unknown" and v.confidence == 0.0
    assert v.ambiguous is True and v.requires_approval is True


def test_priority_flaky_over_infra():
    v = triage(_sig(known_flaky_family=True, mass_cofailure=True, infra_error=True))
    assert v.category == "flaky"  # R1 antes que R2
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.engine`.

- [ ] **Step 3: Implementar**

```python
# src/triage/engine.py
from dataclasses import dataclass

from src.triage.signals import Signals

_APPROVAL_THRESHOLD = 0.80


@dataclass
class TriageVerdict:
    category: str          # flaky | infra | maintenance | real | unknown
    confidence: float
    rule_applied: str
    requires_approval: bool
    llm_assisted: bool
    ambiguous: bool


def triage(signals: Signals) -> TriageVerdict:
    """Clasificación determinista por reglas de prioridad. El ambiguo (R6) queda
    'unknown' + ambiguous=True para que el desempate LLM (F2f) lo resuelva."""
    if signals.retry_passed_in_run or signals.intermittent_same_sha or signals.known_flaky_family:
        return _verdict("flaky", 0.90, "R1_flaky")
    if signals.mass_cofailure and signals.infra_error:
        return _verdict("infra", 0.90, "R2_infra")
    if signals.locator_error and signals.has_green_baseline and signals.dom_changed:
        return _verdict("maintenance", 0.80, "R3_maintenance")
    if signals.assertion_failure and signals.recurrent:
        return _verdict("real", 0.85, "R4_real_recurrent")
    if signals.assertion_failure and signals.novel:
        return _verdict("real", 0.75, "R5_real_novel", novel=True)
    return TriageVerdict(
        category="unknown", confidence=0.0, rule_applied="R6_ambiguous",
        requires_approval=True, llm_assisted=False, ambiguous=True,
    )


def _verdict(category: str, confidence: float, rule: str, *, novel: bool = False) -> TriageVerdict:
    requires_approval = confidence < _APPROVAL_THRESHOLD or (category == "real" and novel)
    return TriageVerdict(
        category=category, confidence=confidence, rule_applied=rule,
        requires_approval=requires_approval, llm_assisted=False, ambiguous=False,
    )
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_engine.py -v`
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/triage/engine.py tests/test_triage_engine.py
git commit -m "feat(triage): motor determinista (reglas R1-R6) + TriageVerdict"
```

---

### Task 4: `evidence.py` — `build_evidence` (bundle auditable)

**Files:**
- Create: `src/triage/evidence.py`
- Test: `tests/test_triage_evidence.py`

**Interfaces:**
- Consumes: `Signals` (Task 2), `TriageVerdict` (Task 3).
- Produces: `build_evidence(*, fingerprint, family_id, lineage_projects, error_type, signals, verdict) -> Dict[str, Any]` — el `evidence_bundle` (fingerprint, family_id, lineage_projects, error_type, signals[{name,value}], rule_applied, category, confidence, requires_approval, llm_assisted).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_triage_evidence.py
from src.triage.engine import triage
from src.triage.evidence import build_evidence
from src.triage.signals import Signals


def _sig(**over):
    base = dict(
        infra_error=False, locator_error=False, assertion_failure=False,
        retry_passed_in_run=False, intermittent_same_sha=False, known_flaky_family=False,
        mass_cofailure=False, has_green_baseline=False, dom_changed=False,
        novel=False, recurrent=False,
    )
    base.update(over)
    return Signals(**base)


def test_evidence_bundle_shape():
    signals = _sig(locator_error=True, has_green_baseline=True, dom_changed=True)
    verdict = triage(signals)
    ev = build_evidence(
        fingerprint="fp1", family_id="fam1", lineage_projects=["proj-a", "proj-b"],
        error_type="TimeoutError", signals=signals, verdict=verdict,
    )
    assert ev["fingerprint"] == "fp1" and ev["family_id"] == "fam1"
    assert ev["lineage_projects"] == ["proj-a", "proj-b"]
    assert ev["error_type"] == "TimeoutError"
    assert ev["rule_applied"] == "R3_maintenance" and ev["category"] == "maintenance"
    assert ev["confidence"] == 0.80 and ev["requires_approval"] is False
    assert ev["llm_assisted"] is False
    names = {s["name"]: s["value"] for s in ev["signals"]}
    assert names["locator_error"] is True and names["dom_changed"] is True
    assert names["infra_error"] is False


def test_evidence_lists_all_signals():
    signals = _sig()
    ev = build_evidence(fingerprint="f", family_id=None, lineage_projects=[],
                        error_type=None, signals=signals, verdict=triage(signals))
    assert len(ev["signals"]) == 11
    assert ev["family_id"] is None and ev["error_type"] is None
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.evidence`.

- [ ] **Step 3: Implementar**

```python
# src/triage/evidence.py
from typing import Any, Dict, List, Optional

from src.triage.engine import TriageVerdict
from src.triage.signals import Signals


def build_evidence(
    *,
    fingerprint: str,
    family_id: Optional[str],
    lineage_projects: List[str],
    error_type: Optional[str],
    signals: Signals,
    verdict: TriageVerdict,
) -> Dict[str, Any]:
    """Bundle auditable: el 'por qué' de la clasificación. Es lo que firmará el
    certificado (F4) y lo que un auditor lee para entender la decisión."""
    return {
        "fingerprint": fingerprint,
        "family_id": family_id,
        "lineage_projects": list(lineage_projects),
        "error_type": error_type,
        "signals": [{"name": name, "value": value} for name, value in _signal_items(signals)],
        "rule_applied": verdict.rule_applied,
        "category": verdict.category,
        "confidence": verdict.confidence,
        "requires_approval": verdict.requires_approval,
        "llm_assisted": verdict.llm_assisted,
    }


def _signal_items(signals: Signals):
    return [
        ("infra_error", signals.infra_error),
        ("locator_error", signals.locator_error),
        ("assertion_failure", signals.assertion_failure),
        ("retry_passed_in_run", signals.retry_passed_in_run),
        ("intermittent_same_sha", signals.intermittent_same_sha),
        ("known_flaky_family", signals.known_flaky_family),
        ("mass_cofailure", signals.mass_cofailure),
        ("has_green_baseline", signals.has_green_baseline),
        ("dom_changed", signals.dom_changed),
        ("novel", signals.novel),
        ("recurrent", signals.recurrent),
    ]
```

- [ ] **Step 4: Ejecutar (pasa) + suite unitaria completa**

Run: `pytest tests/test_triage_evidence.py -v && pytest -m "not integration" -q`
Expected: tests de evidencia PASS; suite unitaria completa verde (sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add src/triage/evidence.py tests/test_triage_evidence.py
git commit -m "feat(triage): build_evidence (bundle auditable)"
```

---

## Self-Review

**1. Cobertura del spec (F2b/F2c):**
- Patrones infra/locator/assertion (§3.1) → Task 1. ✓
- Señales puras desde hechos recuperados (§3.1) → Task 2 (`FailureInput`/`Signals`/`compute_signals`). ✓
- Reglas R1–R6 con confianzas exactas + `requires_approval` (§3.2/§3.3) → Task 3. ✓
- `TriageVerdict` con los 6 campos (§5) → Task 3. ✓
- `evidence_bundle` auditable (§3.4) → Task 4. ✓
- Ambiguo → `unknown`/`ambiguous=True` (lo resuelve F2f) → Task 3. ✓

**2. Placeholders:** ninguno; cada paso lleva código completo y comando con salida esperada.

**3. Consistencia de tipos:** `Signals` (Task 2) lo consumen `triage` (Task 3) y `build_evidence` (Task 4); `TriageVerdict` (Task 3) lo consume `build_evidence` (Task 4); `classify_error` (Task 1) lo usa `compute_signals` (Task 2). Confianzas (0.90/0.90/0.80/0.85/0.75) y `_APPROVAL_THRESHOLD=0.80` coherentes con el spec. `llm_assisted=False` en todo F2c (el LLM es F2f).

**Nota de alcance:** F2b/F2c es el motor PURO. Los hechos de BD que alimentan `FailureInput` (intermitencia, DOM cambiado, label de familia, co-fallo masivo) los recupera la capa de repositorio en **F2d**; el `TriageService` que orquesta carga→señales→motor→evidencia→persistencia y el wiring en el webhook son **F2e**; el desempate LLM de los ambiguos es **F2f**.

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-23-mnemo-autopilot-f2bc-triage-engine.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> Las 4 tareas son **puras** (sin BD/LLM) — todas corren bajo `pytest -m "not integration"`. Continúan en la rama `feat/mnemo-triage` (mismo PR de F2, apilado sobre F1).
