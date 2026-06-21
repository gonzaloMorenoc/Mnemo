# Más formatos de reporte + auto-detección — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir 5 parsers de reporte de test (TestNG, Cucumber, Playwright, Cypress/Mochawesome, Robot Framework) y un detector de formato por contenido con override manual (híbrido), sobre los 2 formatos existentes (Allure, JUnit).

**Architecture:** Cada formato es un parser puro `parse_X(data: bytes, *, project: str) -> List[FailureRecord]` registrado en `IngestionService._PARSERS`. Un nuevo `detect_source(data)` inspecciona el contenido y resuelve el formato cuando `source == "auto"`. El resto de la tubería (sanitizar → fingerprint → embed → `ingest_run`) no cambia. Solo cambia el esquema en el `CHECK` de `test_runs.source`.

**Tech Stack:** Python 3.13, `xml.etree.ElementTree`, `json`, pytest; FastAPI (endpoint); Next.js (un `<select>`); Postgres (una migración).

**Referencia de patrón:** `src/ingest/allure.py`, `src/ingest/junit.py`, `src/ingest/models.py`, `src/defects/ingestion_service.py`.

---

### Task 1: Helper `strip_ansi` en models

Playwright y Cypress incrustan secuencias de color ANSI en los mensajes; hay que limpiarlas para que el fingerprint sea estable.

**Files:**
- Modify: `src/ingest/models.py`
- Test: `tests/test_models_ansi.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_ansi.py
from src.ingest.models import strip_ansi


def test_strip_ansi_removes_color_codes():
    assert strip_ansi("\x1b[31mError\x1b[0m: boom") == "Error: boom"


def test_strip_ansi_noop_on_plain_text():
    assert strip_ansi("plain") == "plain"


def test_strip_ansi_handles_empty():
    assert strip_ansi("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_models_ansi.py -v`
Expected: FAIL with `ImportError: cannot import name 'strip_ansi'`

- [ ] **Step 3: Add the implementation**

In `src/ingest/models.py`, after the existing `_ERR_RE` line, add the regex and function (the module already does `import re`):

```python
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Elimina secuencias de escape ANSI (colores) de un texto."""
    return _ANSI_RE.sub("", text) if text else text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_models_ansi.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/models.py tests/test_models_ansi.py
git commit -m "feat: strip_ansi helper para limpiar colores ANSI de los mensajes"
```

---

### Task 2: Parser TestNG

**Files:**
- Create: `src/ingest/testng.py`
- Test: `tests/test_parse_testng.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parse_testng.py
import pytest

from src.ingest.testng import parse_testng

TESTNG_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<testng-results failed="1" passed="1" total="2">
  <suite name="Suite">
    <test name="Test">
      <class name="com.example.LoginTest">
        <test-method status="PASS" name="testValidLogin"/>
        <test-method status="FAIL" name="testTimeout">
          <exception class="org.openqa.selenium.TimeoutException">
            <message><![CDATA[Expected condition failed: waited 30000ms]]></message>
            <full-stacktrace><![CDATA[org.openqa.selenium.TimeoutException: boom
	at com.example.LoginTest.testTimeout(LoginTest.java:42)]]></full-stacktrace>
          </exception>
        </test-method>
      </class>
    </test>
  </suite>
</testng-results>
"""


def test_parse_testng_returns_only_failures():
    recs = parse_testng(TESTNG_XML, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "com.example.LoginTest.testTimeout"
    assert r.error_type == "org.openqa.selenium.TimeoutException"
    assert "30000ms" in r.message
    assert r.trace and "LoginTest.java:42" in r.trace
    assert r.source == "testng"


def test_parse_testng_invalid_raises():
    with pytest.raises(ValueError):
        parse_testng(b"not xml", project="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_parse_testng.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingest.testng'`

- [ ] **Step 3: Write the implementation**

```python
# src/ingest/testng.py
import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_testng(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un testng-results.xml; devuelve los test-method con status FAIL."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid TestNG XML: {exc}") from exc
    records: List[FailureRecord] = []
    for cls in root.iter("class"):
        classname = cls.get("name") or ""
        for tm in cls.findall("test-method"):
            if (tm.get("status") or "").upper() != "FAIL":
                continue
            name = tm.get("name") or "unknown"
            full = f"{classname}.{name}" if classname else name
            exc_node = tm.find("exception")
            error_type = exc_node.get("class") if exc_node is not None else None
            message = ""
            trace = None
            if exc_node is not None:
                msg_node = exc_node.find("message")
                if msg_node is not None and msg_node.text:
                    message = msg_node.text.strip()
                st_node = exc_node.find("full-stacktrace")
                if st_node is not None and st_node.text:
                    trace = st_node.text.strip() or None
            if not error_type:
                error_type = parse_error_type(message)
            records.append(
                FailureRecord(
                    test_name=full,
                    error_type=error_type,
                    message=message,
                    trace=trace,
                    project=project,
                    source="testng",
                )
            )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_parse_testng.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/testng.py tests/test_parse_testng.py
git commit -m "feat: parser de reportes TestNG"
```

---

### Task 3: Parser Cucumber

**Files:**
- Create: `src/ingest/cucumber.py`
- Test: `tests/test_parse_cucumber.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parse_cucumber.py
import pytest

from src.ingest.cucumber import parse_cucumber

CUCUMBER_JSON = b"""[
  {
    "keyword": "Feature",
    "name": "Login",
    "elements": [
      {
        "keyword": "Scenario",
        "name": "Invalid password",
        "steps": [
          {"keyword": "Given ", "name": "the user is on login", "result": {"status": "passed"}},
          {"keyword": "When ", "name": "submits wrong password",
           "result": {"status": "failed",
                      "error_message": "AssertionError: expected 200 but got 401\\n    at steps.js:12"}}
        ]
      }
    ]
  }
]"""


def test_parse_cucumber_returns_failed_steps():
    recs = parse_cucumber(CUCUMBER_JSON, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "Login / Invalid password"
    assert "expected 200 but got 401" in r.message
    assert r.error_type == "AssertionError"
    assert r.source == "cucumber"


def test_parse_cucumber_invalid_raises():
    with pytest.raises(ValueError):
        parse_cucumber(b"{not json", project="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_parse_cucumber.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingest.cucumber'`

- [ ] **Step 3: Write the implementation**

```python
# src/ingest/cucumber.py
import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_cucumber(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un cucumber.json; devuelve los steps con result.status 'failed'."""
    try:
        features = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Cucumber JSON: {exc}") from exc
    if not isinstance(features, list):
        raise ValueError("Cucumber JSON must be a list of features")
    records: List[FailureRecord] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        fname = feature.get("name") or "Feature"
        for element in feature.get("elements") or []:
            sname = element.get("name") or "Scenario"
            for step in element.get("steps") or []:
                result = step.get("result") or {}
                if (result.get("status") or "").lower() != "failed":
                    continue
                message = (result.get("error_message") or "").strip()
                records.append(
                    FailureRecord(
                        test_name=f"{fname} / {sname}",
                        error_type=parse_error_type(message),
                        message=message,
                        trace=message or None,
                        project=project,
                        source="cucumber",
                    )
                )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_parse_cucumber.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/cucumber.py tests/test_parse_cucumber.py
git commit -m "feat: parser de reportes Cucumber"
```

---

### Task 4: Parser Playwright

Depende de Task 1 (`strip_ansi`).

**Files:**
- Create: `src/ingest/playwright.py`
- Test: `tests/test_parse_playwright.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parse_playwright.py
import pytest

from src.ingest.playwright import parse_playwright

PLAYWRIGHT_JSON = b"""{
  "config": {},
  "suites": [
    {
      "title": "login.spec.ts",
      "specs": [
        {
          "title": "should login",
          "tests": [
            {
              "projectName": "chromium",
              "results": [
                {"status": "passed", "error": {}}
              ]
            }
          ]
        },
        {
          "title": "should logout",
          "tests": [
            {
              "projectName": "chromium",
              "results": [
                {"status": "failed",
                 "error": {"message": "\\u001b[31mError\\u001b[0m: expect(received).toBe(expected)",
                           "stack": "Error: boom\\n    at logout.spec.ts:10"}}
              ]
            }
          ]
        }
      ],
      "suites": []
    }
  ],
  "stats": {"expected": 1, "unexpected": 1}
}"""


def test_parse_playwright_returns_failed_results_without_ansi():
    recs = parse_playwright(PLAYWRIGHT_JSON, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "should logout (chromium)"
    assert "\x1b" not in r.message
    assert "expect(received).toBe(expected)" in r.message
    assert r.trace and "logout.spec.ts:10" in r.trace
    assert r.source == "playwright"


def test_parse_playwright_invalid_raises():
    with pytest.raises(ValueError):
        parse_playwright(b"{bad", project="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_parse_playwright.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingest.playwright'`

- [ ] **Step 3: Write the implementation**

```python
# src/ingest/playwright.py
import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type, strip_ansi

_FAILED = {"failed", "timedout", "interrupted"}


def _walk(suites, project, records: List[FailureRecord]) -> None:
    for suite in suites or []:
        for spec in suite.get("specs") or []:
            title = spec.get("title") or "unknown"
            for test in spec.get("tests") or []:
                pname = test.get("projectName")
                name = f"{title} ({pname})" if pname else title
                for result in test.get("results") or []:
                    if (result.get("status") or "").lower() not in _FAILED:
                        continue
                    err = result.get("error") or {}
                    message = strip_ansi((err.get("message") or "").strip())
                    trace = strip_ansi((err.get("stack") or "").strip()) or None
                    records.append(
                        FailureRecord(
                            test_name=name,
                            error_type=parse_error_type(message),
                            message=message,
                            trace=trace,
                            project=project,
                            source="playwright",
                        )
                    )
        _walk(suite.get("suites"), project, records)


def parse_playwright(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea el JSON del reporter de Playwright; devuelve los results fallidos."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Playwright JSON: {exc}") from exc
    records: List[FailureRecord] = []
    _walk(obj.get("suites") if isinstance(obj, dict) else None, project, records)
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_parse_playwright.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/playwright.py tests/test_parse_playwright.py
git commit -m "feat: parser de reportes Playwright"
```

---

### Task 5: Parser Cypress (Mochawesome)

Depende de Task 1 (`strip_ansi`).

**Files:**
- Create: `src/ingest/cypress.py`
- Test: `tests/test_parse_cypress.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parse_cypress.py
import pytest

from src.ingest.cypress import parse_cypress

MOCHAWESOME_JSON = b"""{
  "stats": {"suites": 1, "tests": 2, "passes": 1, "failures": 1},
  "results": [
    {
      "fullFile": "cypress/e2e/login.cy.js",
      "suites": [
        {
          "title": "Login",
          "tests": [
            {"title": "valid", "fullTitle": "Login valid", "state": "passed", "err": {}},
            {"title": "invalid", "fullTitle": "Login invalid", "state": "failed",
             "err": {"message": "AssertionError: expected 'a' to equal 'b'",
                     "estack": "AssertionError: boom\\n    at login.cy.js:8:10"}}
          ],
          "suites": []
        }
      ],
      "tests": []
    }
  ]
}"""


def test_parse_cypress_returns_failed_tests():
    recs = parse_cypress(MOCHAWESOME_JSON, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "Login invalid"
    assert "expected 'a' to equal 'b'" in r.message
    assert r.trace and "login.cy.js:8" in r.trace
    assert r.source == "cypress"


def test_parse_cypress_invalid_raises():
    with pytest.raises(ValueError):
        parse_cypress(b"nope", project="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_parse_cypress.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingest.cypress'`

- [ ] **Step 3: Write the implementation**

```python
# src/ingest/cypress.py
import json
from typing import List

from src.ingest.models import FailureRecord, parse_error_type, strip_ansi


def _collect(suite, acc: list) -> None:
    for test in suite.get("tests") or []:
        acc.append(test)
    for sub in suite.get("suites") or []:
        _collect(sub, acc)


def parse_cypress(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un JSON Mochawesome (Cypress); devuelve los tests fallidos."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid Mochawesome JSON: {exc}") from exc
    tests: list = []
    for result in (obj.get("results") if isinstance(obj, dict) else None) or []:
        _collect(result, tests)
    records: List[FailureRecord] = []
    for test in tests:
        state = (test.get("state") or "").lower()
        err = test.get("err") or {}
        if state != "failed" and not err:
            continue
        message = strip_ansi((err.get("message") or "").strip())
        trace = strip_ansi((err.get("estack") or "").strip()) or None
        records.append(
            FailureRecord(
                test_name=test.get("fullTitle") or test.get("title") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="cypress",
            )
        )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_parse_cypress.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/cypress.py tests/test_parse_cypress.py
git commit -m "feat: parser de reportes Cypress (Mochawesome)"
```

---

### Task 6: Parser Robot Framework

**Files:**
- Create: `src/ingest/robot.py`
- Test: `tests/test_parse_robot.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parse_robot.py
import pytest

from src.ingest.robot import parse_robot

ROBOT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 6.0">
  <suite name="Login Tests" source="login.robot">
    <test name="Valid Login">
      <status status="PASS"/>
    </test>
    <test name="Timeout Login">
      <kw name="Wait Until Element Is Visible">
        <msg level="FAIL">Element 'id=foo' not visible after 30 seconds</msg>
        <status status="FAIL"/>
      </kw>
      <status status="FAIL">Element 'id=foo' not visible after 30 seconds</status>
    </test>
  </suite>
</robot>
"""


def test_parse_robot_returns_failed_tests():
    recs = parse_robot(ROBOT_XML, project="p")
    assert len(recs) == 1
    r = recs[0]
    assert r.test_name == "Timeout Login"
    assert "not visible after 30 seconds" in r.message
    assert r.source == "robot"


def test_parse_robot_invalid_raises():
    with pytest.raises(ValueError):
        parse_robot(b"<robot", project="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_parse_robot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingest.robot'`

- [ ] **Step 3: Write the implementation**

```python
# src/ingest/robot.py
import xml.etree.ElementTree as ET
from typing import List

from src.ingest.models import FailureRecord, parse_error_type


def parse_robot(data: bytes, *, project: str) -> List[FailureRecord]:
    """Parsea un output.xml de Robot Framework; devuelve los tests con status FAIL."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid Robot XML: {exc}") from exc
    records: List[FailureRecord] = []
    for test in root.iter("test"):
        status = test.find("status")
        if status is None or (status.get("status") or "").upper() != "FAIL":
            continue
        message = (status.text or "").strip()
        fail_msgs = [
            m.text.strip()
            for m in test.iter("msg")
            if (m.get("level") or "").upper() == "FAIL" and m.text
        ]
        if not message and fail_msgs:
            message = fail_msgs[-1]
        trace = "\n".join(fail_msgs) or None
        records.append(
            FailureRecord(
                test_name=test.get("name") or "unknown",
                error_type=parse_error_type(message),
                message=message,
                trace=trace,
                project=project,
                source="robot",
            )
        )
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_parse_robot.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/robot.py tests/test_parse_robot.py
git commit -m "feat: parser de reportes Robot Framework"
```

---

### Task 7: Detector de formato por contenido

**Files:**
- Create: `src/ingest/detect.py`
- Test: `tests/test_detect.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_detect.py
from src.ingest.detect import detect_source

ALLURE = b'[{"name": "t", "status": "failed", "statusDetails": {"message": "x"}}]'
JUNIT = b'<testsuites><testsuite><testcase name="t"><failure>x</failure></testcase></testsuite></testsuites>'
TESTNG = b'<testng-results><suite/></testng-results>'
ROBOT = b'<robot><suite/></robot>'
CUCUMBER = b'[{"keyword": "Feature", "name": "F", "elements": []}]'
PLAYWRIGHT = b'{"config": {}, "suites": [], "stats": {}}'
CYPRESS = b'{"stats": {}, "results": []}'


def test_detect_each_format():
    assert detect_source(ALLURE) == "allure"
    assert detect_source(JUNIT) == "junit"
    assert detect_source(TESTNG) == "testng"
    assert detect_source(ROBOT) == "robot"
    assert detect_source(CUCUMBER) == "cucumber"
    assert detect_source(PLAYWRIGHT) == "playwright"
    assert detect_source(CYPRESS) == "cypress"


def test_detect_garbage_returns_none():
    assert detect_source(b"this is not a report") is None
    assert detect_source(b"") is None


def test_detect_unknown_xml_returns_none():
    assert detect_source(b"<unknown><x/></unknown>") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ingest.detect'`

- [ ] **Step 3: Write the implementation**

```python
# src/ingest/detect.py
import json
import xml.etree.ElementTree as ET
from typing import Optional


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def detect_source(data: bytes, filename: Optional[str] = None) -> Optional[str]:
    """Detecta el formato de un reporte por su contenido. Devuelve el `source` o None.

    El orden de las reglas resuelve los solapamientos (XML vs JSON, y dentro de JSON
    playwright/cypress comparten 'stats', cucumber/allure pueden ser listas).
    """
    # 1) XML por root tag
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        root = None
    if root is not None:
        tag = _localname(root.tag)
        if tag == "testng-results":
            return "testng"
        if tag == "robot":
            return "robot"
        if tag in ("testsuite", "testsuites"):
            return "junit"
        return None
    # 2) JSON por estructura
    try:
        obj = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(obj, dict):
        if "suites" in obj and "stats" in obj:
            return "playwright"
        if "results" in obj and "stats" in obj:
            return "cypress"
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and "elements" in obj[0]:
        return "cucumber"
    items = obj if isinstance(obj, list) else [obj]
    if items and isinstance(items[0], dict):
        first = items[0]
        if "statusDetails" in first or (
            "status" in first and ("uuid" in first or "fullName" in first)
        ):
            return "allure"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_detect.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ingest/detect.py tests/test_detect.py
git commit -m "feat: detector de formato de reporte por contenido"
```

---

### Task 8: Wiring en IngestionService (registro + auto)

**Files:**
- Modify: `src/defects/ingestion_service.py`
- Test: `tests/test_ingestion_service_formats.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestion_service_formats.py
import pytest

from src.defects.ingestion_service import IngestionService

TESTNG_XML = b"""<?xml version="1.0"?>
<testng-results>
  <suite name="S"><test name="T"><class name="C">
    <test-method status="FAIL" name="m">
      <exception class="E"><message><![CDATA[boom 30000ms]]></message></exception>
    </test-method>
  </class></test></suite>
</testng-results>"""


class _FakeEmbedder:
    def embed(self, text):
        return [0.1] * 384


class _CapturingRepo:
    def __init__(self):
        self.captured = None

    def ingest_run(self, *, user_id, org_id, project, source, items):
        self.captured = {"source": source, "items": items}
        return {"run_id": "r", "ingested": len(items), "known": 0, "novel": len(items)}


def _service():
    repo = _CapturingRepo()
    return IngestionService(repo=repo, embedder=_FakeEmbedder()), repo


def test_ingest_report_auto_detects_testng():
    service, repo = _service()
    service.ingest_report(user_id="u", org_id="o", project="p", source="auto", data=TESTNG_XML)
    assert repo.captured["source"] == "testng"
    assert len(repo.captured["items"]) == 1


def test_ingest_report_auto_unknown_raises():
    service, _ = _service()
    with pytest.raises(ValueError):
        service.ingest_report(user_id="u", org_id="o", project="p", source="auto",
                              data=b"not a report")


def test_ingest_report_explicit_source_used():
    service, repo = _service()
    service.ingest_report(user_id="u", org_id="o", project="p", source="testng", data=TESTNG_XML)
    assert repo.captured["source"] == "testng"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingestion_service_formats.py -v`
Expected: FAIL — `test_ingest_report_auto_detects_testng` raises `ValueError: unsupported source: auto` (the registry/auto handling does not exist yet)

- [ ] **Step 3: Update the implementation**

Replace the imports and `_PARSERS` block at the top of `src/defects/ingestion_service.py`:

```python
from dataclasses import replace
from typing import Any, Dict

from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.allure import parse_allure
from src.ingest.cucumber import parse_cucumber
from src.ingest.cypress import parse_cypress
from src.ingest.detect import detect_source
from src.ingest.junit import parse_junit
from src.ingest.playwright import parse_playwright
from src.ingest.robot import parse_robot
from src.ingest.testng import parse_testng
from src.sanitizer import sanitize_text

_PARSERS = {
    "allure": parse_allure,
    "junit": parse_junit,
    "testng": parse_testng,
    "cucumber": parse_cucumber,
    "playwright": parse_playwright,
    "cypress": parse_cypress,
    "robot": parse_robot,
}
```

Then, in `ingest_report`, replace the parser-selection lines at the start of the method body (currently `parser = _PARSERS.get(source)` … `records = parser(data, project=project)`) with:

```python
        if source == "auto":
            detected = detect_source(data)
            if detected is None:
                raise ValueError(
                    "no se reconoció el formato; selecciónalo manualmente"
                )
            source = detected
        parser = _PARSERS.get(source)
        if parser is None:
            raise ValueError(f"unsupported source: {source}")
        records = parser(data, project=project)
```

(The rest of the method — sanitize, fingerprint, embed, and `self.repo.ingest_run(..., source=source, ...)` — is unchanged; note `source` is now the resolved value, never `"auto"`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingestion_service_formats.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full unit suite to catch regressions**

Run: `python3 -m pytest -m "not integration" -q`
Expected: PASS (all previously-passing tests still green)

- [ ] **Step 6: Commit**

```bash
git add src/defects/ingestion_service.py tests/test_ingestion_service_formats.py
git commit -m "feat: registra los nuevos parsers y resuelve source=auto via detector"
```

---

### Task 9: Migración del CHECK + endpoint acepta "auto"

**Files:**
- Create: `db/migrations/004_more_sources.sql`
- Modify: `src/api_v2.py:227`

- [ ] **Step 1: Write the migration**

```sql
-- db/migrations/004_more_sources.sql
-- Amplía los formatos de reporte admitidos en test_runs.source.
alter table public.test_runs drop constraint test_runs_source_check;
alter table public.test_runs add constraint test_runs_source_check
    check (source in ('allure', 'junit', 'testng', 'cucumber', 'playwright', 'cypress', 'robot'));
```

- [ ] **Step 2: Apply the migration to Supabase**

Run:
```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg
sql = open('db/migrations/004_more_sources.sql').read()
with psycopg.connect(os.getenv('DATABASE_URL','')) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute('select pg_get_constraintdef(oid) from pg_constraint where conname=%s', ('test_runs_source_check',))
        print(cur.fetchone()[0])
    conn.commit()
"
```
Expected: prints a CHECK definition listing all 7 sources.

- [ ] **Step 3: Make the endpoint default `source` to "auto"**

In `src/api_v2.py`, change the `ingest_report_v2` signature line:

```python
    source: str = Form("auto"),
```

(Was `source: str = Form(...)`. Everything else in the endpoint is unchanged; `ValueError` from an unrecognized auto-detect already maps to HTTP 400.)

- [ ] **Step 4: Verify the API module still imports**

Run: `python3 -c "import src.api_v2"`
Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add db/migrations/004_more_sources.sql src/api_v2.py
git commit -m "feat: amplía el CHECK de source a 7 formatos y default source=auto"
```

---

### Task 10: Frontend — selector con "Auto-detectar"

**Files:**
- Modify: `frontend/src/app/app/assurance/page.tsx:17` (estado) y el bloque `<select id="source">`

- [ ] **Step 1: Default the source state to "auto"**

In `frontend/src/app/app/assurance/page.tsx`, change:

```tsx
  const [source, setSource] = useState("auto");
```

(Was `useState("allure")`.)

- [ ] **Step 2: Replace the `<select>` options**

Replace the two existing `<option>` lines inside `<select id="source">` with:

```tsx
              <option value="auto">Auto-detectar</option>
              <option value="allure">Allure (JSON)</option>
              <option value="junit">JUnit (XML)</option>
              <option value="testng">TestNG (XML)</option>
              <option value="cucumber">Cucumber (JSON)</option>
              <option value="playwright">Playwright (JSON)</option>
              <option value="cypress">Cypress / Mochawesome (JSON)</option>
              <option value="robot">Robot Framework (XML)</option>
```

- [ ] **Step 3: Verify typecheck and lint pass**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/app/assurance/page.tsx
git commit -m "feat: selector de formato con auto-detección en Assurance"
```

---

### Task 11: Verificación end-to-end del backend

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest -m "not integration" -q`
Expected: all green (the 90 pre-existing + the new parser/detector/service tests).

- [ ] **Step 2: Run the integration suite (requires `DATABASE_URL`)**

Run: `python3 -m pytest -m integration -q`
Expected: all green (6 assurance repository tests; unaffected by this change).

- [ ] **Step 3: Smoke-test auto-detection across formats**

Run:
```bash
python3 -c "
from src.ingest.detect import detect_source
samples = {
  'allure': b'[{\"status\":\"failed\",\"statusDetails\":{\"message\":\"x\"}}]',
  'junit': b'<testsuites><testsuite/></testsuites>',
  'testng': b'<testng-results/>',
  'robot': b'<robot/>',
  'cucumber': b'[{\"keyword\":\"Feature\",\"elements\":[]}]',
  'playwright': b'{\"suites\":[],\"stats\":{}}',
  'cypress': b'{\"results\":[],\"stats\":{}}',
}
for want, data in samples.items():
    got = detect_source(data)
    assert got == want, f'{want} -> {got}'
print('auto-detección OK para los 7 formatos')
"
```
Expected: `auto-detección OK para los 7 formatos`

---

## Notas de implementación

- **TDD estricto**: cada parser sigue RED → GREEN → commit. No escribas el parser antes que su test.
- **YAGNI**: no añadas campos a `FailureRecord` ni soporto de namespaces XML más allá de `_localname`. Un bug de Jira (Slice 2) tendrá su propio diseño.
- **Robot Framework**: este plan asume `output.xml` clásico (v5/6) donde el `<test>` tiene un `<status>` hijo directo con el mensaje. Si una fixture real de v7 difiere, ajusta la fixture y el parser en el mismo task.
- **Orden**: Task 1 antes que 4 y 5 (usan `strip_ansi`). Task 8 después de 1-7. El resto es independiente.
