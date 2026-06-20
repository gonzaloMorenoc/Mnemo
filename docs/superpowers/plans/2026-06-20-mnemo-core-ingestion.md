# Mnemo — Núcleo de ingesta (Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el núcleo puro de ingesta de Mnemo — parsers de reportes Allure/JUnit, fingerprint determinista de fallos y la lógica de decisión de matching de familias de defecto — todo como funciones puras testeables sin BD ni LLM.

**Architecture:** Módulos pequeños y enfocados bajo `src/ingest/` y `src/defects/`. Sin dependencias de infraestructura: parsers (JSON/XML → `FailureRecord`), `fingerprint` (normaliza partes volátiles → firma sha1), `decide_match` (decisión pura coseno/firma). La persistencia, endpoints, LLM y frontend van en planes posteriores.

**Tech Stack:** Python 3.13, pytest. Solo stdlib (`json`, `xml.etree`, `re`, `hashlib`, `math`).

**Branch:** `feat/mnemo-assurance` (ya creada). Spec: `docs/superpowers/specs/2026-06-20-mnemo-assurance-platform-design.md`. Ejecutar todo con `python3` desde la raíz del repo `/Users/gonzalo/Documents/GitHub/SmartErrorDebugger`.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/ingest/__init__.py` | Paquete de ingesta (vacío) |
| `src/ingest/models.py` | `FailureRecord` (dataclass) + `parse_error_type()` |
| `src/ingest/allure.py` | `parse_allure(data, *, project)` — Allure result JSON → records |
| `src/ingest/junit.py` | `parse_junit(data, *, project)` — JUnit XML → records |
| `src/defects/__init__.py` | Paquete de defectos (vacío) |
| `src/defects/fingerprint.py` | `normalize()` + `fingerprint(rec)` — firma determinista |
| `src/defects/match.py` | `FamilyCandidate`, `MatchResult`, `decide_match()` — decisión pura |
| `tests/test_ingest_models.py` | tests de `parse_error_type` |
| `tests/test_ingest_allure.py` | tests del parser Allure |
| `tests/test_ingest_junit.py` | tests del parser JUnit |
| `tests/test_fingerprint.py` | tests de normalización y determinismo |
| `tests/test_match.py` | tests de la decisión de matching |

---

## Task 1: FailureRecord + parse_error_type

**Files:**
- Create: `src/ingest/__init__.py`, `src/ingest/models.py`
- Test: `tests/test_ingest_models.py`

- [ ] **Step 1: Create the empty package file**

Create `src/ingest/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

Create `tests/test_ingest_models.py`:
```python
from src.ingest.models import FailureRecord, parse_error_type


def test_parse_error_type_finds_exception():
    assert parse_error_type("org.openqa.selenium.TimeoutException: wait 30s") == "org.openqa.selenium.TimeoutException"


def test_parse_error_type_finds_error():
    assert parse_error_type("AssertionError: expected 200 but got 500") == "AssertionError"


def test_parse_error_type_none_when_absent():
    assert parse_error_type("something went wrong") is None
    assert parse_error_type("") is None


def test_failure_record_fields():
    rec = FailureRecord(test_name="t", error_type=None, message="m", trace=None, project="p", source="allure")
    assert rec.test_name == "t" and rec.project == "p" and rec.source == "allure"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.ingest.models'`.

- [ ] **Step 4: Implement `src/ingest/models.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingest_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/ingest/__init__.py src/ingest/models.py tests/test_ingest_models.py
git commit -m "feat: add FailureRecord and parse_error_type for Mnemo ingestion"
```

---

## Task 2: Allure parser

**Files:**
- Create: `src/ingest/allure.py`
- Test: `tests/test_ingest_allure.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest_allure.py`:
```python
import json

from src.ingest.allure import parse_allure


def test_parse_allure_extracts_only_failures():
    data = json.dumps([
        {"name": "test_login", "status": "failed",
         "statusDetails": {"message": "TimeoutException: 30s", "trace": "at Foo.java:42"}},
        {"name": "test_ok", "status": "passed", "statusDetails": {}},
        {"name": "test_skip", "status": "skipped", "statusDetails": {}},
        {"name": "test_broken", "status": "broken",
         "statusDetails": {"message": "NullPointerException", "trace": "at Bar.java:7"}},
    ]).encode()
    recs = parse_allure(data, project="proj-a")
    assert len(recs) == 2
    names = {r.test_name for r in recs}
    assert names == {"test_login", "test_broken"}
    login = next(r for r in recs if r.test_name == "test_login")
    assert login.source == "allure"
    assert login.project == "proj-a"
    assert login.error_type == "TimeoutException"
    assert "30s" in login.message
    assert login.trace == "at Foo.java:42"


def test_parse_allure_accepts_single_object():
    data = json.dumps({"name": "t", "status": "failed", "statusDetails": {"message": "X"}}).encode()
    recs = parse_allure(data, project="p")
    assert len(recs) == 1 and recs[0].test_name == "t"


def test_parse_allure_handles_missing_fields():
    data = json.dumps([{"status": "failed"}]).encode()
    recs = parse_allure(data, project="p")
    assert len(recs) == 1
    assert recs[0].test_name == "unknown"
    assert recs[0].message == ""
    assert recs[0].trace is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_allure.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.ingest.allure'`.

- [ ] **Step 3: Implement `src/ingest/allure.py`**

```python
import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type

FAILED_STATUSES = {"failed", "broken"}


def parse_allure(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea uno o varios Allure result objects; devuelve solo failed/broken."""
    obj = json.loads(data)
    items = obj if isinstance(obj, list) else [obj]
    records: List[FailureRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = (item.get("status") or "").lower()
        if status not in FAILED_STATUSES:
            continue
        details = item.get("statusDetails") or {}
        message = (details.get("message") or "").strip()
        trace = details.get("trace") or None
        records.append(
            FailureRecord(
                test_name=item.get("name") or item.get("fullName") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="allure",
            )
        )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingest_allure.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/ingest/allure.py tests/test_ingest_allure.py
git commit -m "feat: add Allure report parser"
```

---

## Task 3: JUnit parser

**Files:**
- Create: `src/ingest/junit.py`
- Test: `tests/test_ingest_junit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest_junit.py`:
```python
from src.ingest.junit import parse_junit

JUNIT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite" tests="3" failures="1" errors="1">
  <testcase classname="LoginTest" name="test_login">
    <failure message="AssertionError: expected 200" type="AssertionError">at Login.py:10</failure>
  </testcase>
  <testcase classname="ApiTest" name="test_call">
    <error message="ConnectionError: refused" type="ConnectionError">at Api.py:22</error>
  </testcase>
  <testcase classname="OkTest" name="test_ok"/>
</testsuite>"""


def test_parse_junit_extracts_failures_and_errors():
    recs = parse_junit(JUNIT_XML, project="proj-b")
    assert len(recs) == 2
    names = {r.test_name for r in recs}
    assert names == {"LoginTest.test_login", "ApiTest.test_call"}
    login = next(r for r in recs if r.test_name == "LoginTest.test_login")
    assert login.source == "junit"
    assert login.project == "proj-b"
    assert login.error_type == "AssertionError"
    assert login.trace == "at Login.py:10"


def test_parse_junit_falls_back_to_message_for_type():
    xml = b'<testsuite><testcase name="t"><failure message="TimeoutException: x">trace</failure></testcase></testsuite>'
    recs = parse_junit(xml, project="p")
    assert recs[0].error_type == "TimeoutException"
    assert recs[0].test_name == "t"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_junit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.ingest.junit'`.

- [ ] **Step 3: Implement `src/ingest/junit.py`**

```python
import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_junit(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea JUnit XML; devuelve testcases con <failure> o <error>."""
    root = ET.fromstring(data)
    records: List[FailureRecord] = []
    for tc in root.iter("testcase"):
        node = tc.find("failure")
        if node is None:
            node = tc.find("error")
        if node is None:
            continue
        name = tc.get("name") or "unknown"
        classname = tc.get("classname")
        full = f"{classname}.{name}" if classname else name
        message = (node.get("message") or "").strip()
        error_type = node.get("type") or parse_error_type(message)
        trace = (node.text or "").strip() or None
        records.append(
            FailureRecord(
                test_name=full,
                error_type=error_type,
                message=message,
                trace=trace,
                project=project,
                source="junit",
            )
        )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingest_junit.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/ingest/junit.py tests/test_ingest_junit.py
git commit -m "feat: add JUnit report parser"
```

---

## Task 4: Fingerprint determinista

**Files:**
- Create: `src/defects/__init__.py`, `src/defects/fingerprint.py`
- Test: `tests/test_fingerprint.py`

- [ ] **Step 1: Create the empty package file**

Create `src/defects/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

Create `tests/test_fingerprint.py`:
```python
from src.ingest.models import FailureRecord
from src.defects.fingerprint import normalize, fingerprint


def test_normalize_strips_volatile_parts():
    n = normalize("Timeout after 30000ms at 0xAB12 id 550e8400-e29b-41d4-a716-446655440000 /tmp/x/y.log")
    assert "<n>" in n and "<hex>" in n and "<uuid>" in n and "<path>" in n
    assert "30000" not in n


def _rec(msg, trace):
    return FailureRecord(test_name="t", error_type="TimeoutException", message=msg, trace=trace, project="p", source="allure")


def test_fingerprint_is_stable_across_volatile_differences():
    a = _rec("TimeoutException after 30000ms (id 550e8400-e29b-41d4-a716-446655440000)", "at Foo.java:42")
    b = _rec("TimeoutException after 45000ms (id 11111111-2222-3333-4444-555555555555)", "at Foo.java:99")
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_differs_for_different_errors():
    a = _rec("TimeoutException waiting for element", "at Foo.java:42")
    b = _rec("NullPointerException on submit", "at Bar.java:7")
    assert fingerprint(a) != fingerprint(b)


def test_fingerprint_is_hex_sha1():
    fp = fingerprint(_rec("X", None))
    assert len(fp) == 40 and all(c in "0123456789abcdef" for c in fp)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fingerprint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.defects.fingerprint'`.

- [ ] **Step 4: Implement `src/defects/fingerprint.py`**

```python
import hashlib
import re
from typing import Optional

from src.ingest.models import FailureRecord

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_PATH = re.compile(r"(?:/[\w.\-]+){2,}")
_NUM = re.compile(r"\b\d+\b")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Elimina partes volatiles (uuid, hex, paths, numeros) para una firma estable."""
    if not text:
        return ""
    t = _UUID.sub("<uuid>", text)
    t = _HEX.sub("<hex>", t)
    t = _PATH.sub("<path>", t)
    t = _NUM.sub("<n>", t)
    t = _WS.sub(" ", t).strip().lower()
    return t


def _top_frame(trace: Optional[str]) -> str:
    if not trace:
        return ""
    for raw in trace.splitlines():
        line = raw.strip()
        if line.startswith("at ") or " line " in line or 'File "' in line:
            return normalize(line)
    return ""


def fingerprint(rec: FailureRecord) -> str:
    """Firma sha1 determinista a partir de tipo de error + mensaje normalizado + top frame."""
    head = normalize(rec.message)[:200]
    basis = "|".join([(rec.error_type or "").lower(), head, _top_frame(rec.trace)])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_fingerprint.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/defects/__init__.py src/defects/fingerprint.py tests/test_fingerprint.py
git commit -m "feat: add deterministic failure fingerprint"
```

---

## Task 5: Decisión de matching (pura)

**Files:**
- Create: `src/defects/match.py`
- Test: `tests/test_match.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_match.py`:
```python
from src.defects.match import FamilyCandidate, decide_match


def test_exact_fingerprint_match_wins():
    cands = [FamilyCandidate(family_id="f1", signature="abc", centroid=[0.0, 1.0])]
    res = decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=cands)
    assert res.family_id == "f1" and res.is_new is False and res.score == 1.0


def test_cosine_match_over_threshold():
    cands = [FamilyCandidate(family_id="f1", signature="zzz", centroid=[1.0, 0.0])]
    res = decide_match(fingerprint="abc", embedding=[0.99, 0.01], candidates=cands, threshold=0.85)
    assert res.family_id == "f1" and res.is_new is False and res.score >= 0.85


def test_new_family_when_below_threshold():
    cands = [FamilyCandidate(family_id="f1", signature="zzz", centroid=[1.0, 0.0])]
    res = decide_match(fingerprint="abc", embedding=[0.0, 1.0], candidates=cands, threshold=0.85)
    assert res.family_id is None and res.is_new is True


def test_new_family_when_no_candidates():
    res = decide_match(fingerprint="abc", embedding=[1.0, 0.0], candidates=[])
    assert res.is_new is True and res.family_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_match.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.defects.match'`.

- [ ] **Step 3: Implement `src/defects/match.py`**

```python
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence


@dataclass
class FamilyCandidate:
    family_id: str
    signature: str
    centroid: Sequence[float]


@dataclass
class MatchResult:
    family_id: Optional[str]  # None => crear familia nueva
    is_new: bool
    score: float


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def decide_match(*, fingerprint: str, embedding: Sequence[float],
                 candidates: List[FamilyCandidate], threshold: float = 0.85) -> MatchResult:
    """Empareja un fallo con una familia: firma exacta primero, luego mejor coseno >= threshold."""
    for cand in candidates:
        if cand.signature == fingerprint:
            return MatchResult(family_id=cand.family_id, is_new=False, score=1.0)

    best: Optional[FamilyCandidate] = None
    best_score = 0.0
    for cand in candidates:
        score = _cosine(embedding, cand.centroid)
        if score > best_score:
            best, best_score = cand, score

    if best is not None and best_score >= threshold:
        return MatchResult(family_id=best.family_id, is_new=False, score=best_score)
    return MatchResult(family_id=None, is_new=True, score=best_score)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_match.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/defects/match.py tests/test_match.py
git commit -m "feat: add pure defect-family match decision"
```

---

## Task 6: Verificación final del núcleo

**Files:** ninguno nuevo.

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest -m "not integration" -q`
Expected: PASS — incluye los nuevos `test_ingest_models/allure/junit`, `test_fingerprint`, `test_match`, más los previos de `/v2`.

- [ ] **Step 2: Clean-import check**

Run: `python3 -c "import src.ingest.allure, src.ingest.junit, src.defects.fingerprint, src.defects.match; print('mnemo core imports OK')"`
Expected: `mnemo core imports OK`.

- [ ] **Step 3: Code review**

Lanzar el agente `code-reviewer`/`python-reviewer` sobre el diff de las 5 tareas. Atender CRITICAL/HIGH.

---

## Próximos planes (no en este)

- **Plan 2:** migración `002_assurance.sql` (`test_runs`/`failures`/`defect_families` + FORCE RLS) + repositorio de persistencia (centroide running-mean, contadores) + endpoints `POST /v2/ingest/report`, `GET /v2/defects`, `GET /v2/defects/{id}`.
- **Plan 3:** `src/assurance/report.py` (veredicto known/novel + narrativa LLM async) + `GET /v2/assurance/run/{id}`.
- **Plan 4:** frontend (páginas Assurance + Defect DNA).
- **Plan 5:** documentación (`docs/functional`, `docs/technical`, ADR) + poda legacy + `scripts/seed_demo.py`.
