# Conector de bugs de Jira → Defect DNA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar los issues de tipo Bug de Jira en el Defect DNA por dos vías (export de archivo y API en vivo), reutilizando el pipeline existente con `source="jira"`.

**Architecture:** Un módulo nuevo `src/jira/` con responsabilidades separadas (modelos, export, mapper, validación SSRF, cifrado, cliente API, repositorio de integraciones, servicio de ingesta). Ambas vías producen `List[JiraBug]`, que un mapper convierte en `IngestItem` (con `external_ref`/`external_url`) y entrega a `AssuranceRepository.ingest_run(source="jira")`. Credenciales por org cifradas con Fernet.

**Tech Stack:** Python 3.13, `atlassian-python-api` (cliente Jira, ya en requirements), `cryptography` (Fernet, nueva), `csv`/`json` stdlib, pytest; FastAPI (endpoints); Postgres (migración 005); Next.js (página de integraciones).

**Referencia de patrón:** `src/defects/ingestion_service.py`, `src/defects/repository.py`, `src/api_v2.py` (deps lazy + mapeo de errores), `src/ingest/models.py`.

---

### Task 1: Dependencia `cryptography`

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the dependency** — append to `requirements.txt`:

```
cryptography==44.0.0
```

- [ ] **Step 2: Install and verify the import**

Run: `python3 -m pip install 'cryptography==44.0.0' && python3 -c "from cryptography.fernet import Fernet; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: añade cryptography (Fernet) para cifrar credenciales"
```

---

### Task 2: `JiraBug` model + `adf_to_text`

**Files:**
- Create: `src/jira/__init__.py` (empty)
- Create: `src/jira/models.py`
- Test: `tests/test_jira_models.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_models.py`:

```python
from src.jira.models import JiraBug, adf_to_text


def test_jirabug_defaults_url_empty():
    b = JiraBug(key="P-1", summary="s", description="d", issue_type="Bug", status="Open")
    assert b.url == ""


def test_adf_to_text_flattens_nested_doc():
    adf = {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Login"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "timeout 30s"}]},
    ]}
    assert adf_to_text(adf) == "Login timeout 30s"


def test_adf_to_text_passthrough_and_none():
    assert adf_to_text("plain text") == "plain text"
    assert adf_to_text(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira'`

- [ ] **Step 3: Create the package and the module**

Create empty `src/jira/__init__.py`. Then create `src/jira/models.py`:

```python
from dataclasses import dataclass
from typing import Any


@dataclass
class JiraBug:
    key: str
    summary: str
    description: str
    issue_type: str
    status: str
    url: str = ""


def adf_to_text(value: Any) -> str:
    """Aplana una descripción de Jira: ADF (dict) → texto plano; str → str; None → ''."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return " ".join(parts).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/__init__.py src/jira/models.py tests/test_jira_models.py
git commit -m "feat: modelo JiraBug y adf_to_text"
```

---

### Task 3: `parse_jira_export` (CSV + JSON)

**Files:**
- Create: `src/jira/export.py`
- Test: `tests/test_jira_export.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_export.py`:

```python
import pytest

from src.jira.export import parse_jira_export

SEARCH_JSON = b"""{
  "issues": [
    {"key": "PROJ-1", "fields": {"summary": "Login timeout",
      "description": {"type": "doc", "content": [{"type": "paragraph",
        "content": [{"type": "text", "text": "waited 30000ms"}]}]},
      "issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
    {"key": "PROJ-2", "fields": {"summary": "A story",
      "description": "ignore me", "issuetype": {"name": "Story"},
      "status": {"name": "Done"}}}
  ]
}"""

CSV_EXPORT = (
    b"Issue key,Summary,Description,Issue Type,Status\r\n"
    b"PROJ-9,Checkout fails,NullPointer in pay,Bug,Open\r\n"
    b"PROJ-10,Nice to have,whatever,Story,Backlog\r\n"
)


def test_parse_export_json_only_bugs():
    bugs = parse_jira_export(SEARCH_JSON)
    assert len(bugs) == 1
    assert bugs[0].key == "PROJ-1"
    assert "30000ms" in bugs[0].description
    assert bugs[0].issue_type == "Bug"


def test_parse_export_csv_only_bugs():
    bugs = parse_jira_export(CSV_EXPORT)
    assert len(bugs) == 1
    assert bugs[0].key == "PROJ-9"
    assert bugs[0].summary == "Checkout fails"
    assert bugs[0].status == "Open"


def test_parse_export_invalid_raises():
    with pytest.raises(ValueError):
        parse_jira_export(b"definitely not jira")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.export'`

- [ ] **Step 3: Write the implementation** — create `src/jira/export.py`:

```python
import csv
import io
import json
from typing import List

from src.jira.models import JiraBug, adf_to_text


def _from_search_json(obj: dict) -> List[JiraBug]:
    bugs: List[JiraBug] = []
    for issue in obj.get("issues") or []:
        fields = issue.get("fields") or {}
        itype = (fields.get("issuetype") or {}).get("name") or ""
        if itype.lower() != "bug":
            continue
        bugs.append(JiraBug(
            key=issue.get("key") or "",
            summary=(fields.get("summary") or "").strip(),
            description=adf_to_text(fields.get("description")),
            issue_type=itype,
            status=(fields.get("status") or {}).get("name") or "",
        ))
    return bugs


def _from_csv(text: str) -> List[JiraBug]:
    bugs: List[JiraBug] = []
    for row in csv.DictReader(io.StringIO(text)):
        itype = (row.get("Issue Type") or "").strip()
        if itype.lower() != "bug":
            continue
        bugs.append(JiraBug(
            key=(row.get("Issue key") or "").strip(),
            summary=(row.get("Summary") or "").strip(),
            description=(row.get("Description") or "").strip(),
            issue_type=itype,
            status=(row.get("Status") or "").strip(),
        ))
    return bugs


def parse_jira_export(data: bytes) -> List[JiraBug]:
    """Parsea un export de Jira: JSON de /rest/api/3/search o CSV estándar. Solo Bugs."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Invalid Jira export encoding: {exc}") from exc
    stripped = text.lstrip()
    if stripped[:1] == "{":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Jira JSON: {exc}") from exc
        return _from_search_json(obj)
    first_line = stripped.splitlines()[0] if stripped else ""
    if "Issue key" not in first_line:
        raise ValueError("Unrecognized Jira export (expected search JSON or CSV with 'Issue key')")
    return _from_csv(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_export.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/export.py tests/test_jira_export.py
git commit -m "feat: parser de export de Jira (JSON search + CSV)"
```

---

### Task 4: `bug_to_record` mapper

**Files:**
- Create: `src/jira/mapper.py`
- Test: `tests/test_jira_mapper.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_mapper.py`:

```python
from src.jira.mapper import bug_to_record
from src.jira.models import JiraBug


def test_bug_to_record_maps_fields():
    bug = JiraBug(key="PROJ-1", summary="Login timeout", description="waited 30s",
                  issue_type="Bug", status="Open", url="https://x/browse/PROJ-1")
    rec = bug_to_record(bug, project="cliente-a")
    assert rec.test_name == "PROJ-1"
    assert rec.error_type == "Bug"
    assert rec.message == "Login timeout"
    assert rec.trace == "waited 30s"
    assert rec.project == "cliente-a"
    assert rec.source == "jira"


def test_bug_to_record_empty_description_is_none():
    bug = JiraBug(key="P-2", summary="s", description="", issue_type="Bug", status="Open")
    rec = bug_to_record(bug, project="p")
    assert rec.trace is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_mapper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.mapper'`

- [ ] **Step 3: Write the implementation** — create `src/jira/mapper.py`:

```python
from src.ingest.models import FailureRecord
from src.jira.models import JiraBug


def bug_to_record(bug: JiraBug, *, project: str) -> FailureRecord:
    """Mapea un JiraBug a un FailureRecord sintético (source='jira')."""
    return FailureRecord(
        test_name=bug.key or "unknown",
        error_type=bug.issue_type or None,
        message=bug.summary,
        trace=bug.description or None,
        project=project,
        source="jira",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_mapper.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/mapper.py tests/test_jira_mapper.py
git commit -m "feat: mapper bug_to_record (Jira → FailureRecord sintético)"
```

---

### Task 5: `validate_base_url` (protección SSRF)

**Files:**
- Create: `src/jira/safe_url.py`
- Test: `tests/test_jira_safe_url.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_safe_url.py`:

```python
import pytest

from src.jira import safe_url
from src.jira.safe_url import validate_base_url


def _fake_resolve(ip):
    def _resolver(host, port, *a, **k):
        return [(2, 1, 6, "", (ip, port or 443))]
    return _resolver


def test_accepts_public_https(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    assert validate_base_url("https://acme.atlassian.net/") == "https://acme.atlassian.net"


def test_rejects_http(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    with pytest.raises(ValueError):
        validate_base_url("http://acme.atlassian.net")


def test_rejects_loopback(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("127.0.0.1"))
    with pytest.raises(ValueError):
        validate_base_url("https://localhost")


def test_rejects_private(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("10.0.0.5"))
    with pytest.raises(ValueError):
        validate_base_url("https://internal.jira")


def test_rejects_metadata(monkeypatch):
    monkeypatch.setattr(safe_url.socket, "getaddrinfo", _fake_resolve("169.254.169.254"))
    with pytest.raises(ValueError):
        validate_base_url("https://evil.example")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_safe_url.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.safe_url'`

- [ ] **Step 3: Write the implementation** — create `src/jira/safe_url.py`:

```python
import ipaddress
import socket
from urllib.parse import urlparse


def validate_base_url(url: str) -> str:
    """Valida la URL base de Jira contra SSRF. Devuelve la URL normalizada o ValueError."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("La URL de Jira debe usar https")
    host = parsed.hostname
    if not host:
        raise ValueError("URL de Jira sin host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"No se pudo resolver el host de Jira: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError("La URL de Jira apunta a una dirección no permitida")
    return url.strip().rstrip("/")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_safe_url.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/safe_url.py tests/test_jira_safe_url.py
git commit -m "feat: validación SSRF de la base_url de Jira"
```

---

### Task 6: Cifrado del token (Fernet)

**Files:**
- Create: `src/jira/crypto.py`
- Test: `tests/test_jira_crypto.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_crypto.py`:

```python
import pytest
from cryptography.fernet import Fernet

from src.jira.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("MNEMO_SECRET_KEY", Fernet.generate_key().decode())
    enc = encrypt_token("super-secret-token")
    assert enc != "super-secret-token"
    assert decrypt_token(enc) == "super-secret-token"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MNEMO_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        encrypt_token("x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.crypto'`

- [ ] **Step 3: Write the implementation** — create `src/jira/crypto.py`:

```python
import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.getenv("MNEMO_SECRET_KEY", "")
    if not key:
        raise RuntimeError(
            "MNEMO_SECRET_KEY no está configurada (requerida para cifrar credenciales)"
        )
    return Fernet(key.encode("utf-8"))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(enc: str) -> str:
    return _fernet().decrypt(enc.encode("utf-8")).decode("utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_crypto.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/crypto.py tests/test_jira_crypto.py
git commit -m "feat: cifrado Fernet de credenciales (MNEMO_SECRET_KEY)"
```

---

### Task 7: `JiraApiClient` (API en vivo)

**Files:**
- Create: `src/jira/client.py`
- Test: `tests/test_jira_client.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_client.py`:

```python
import pytest

from src.jira.client import JiraApiClient, JiraApiError


class _FakeJira:
    """Imita atlassian.Jira: devuelve 2 páginas y luego vacío."""

    def __init__(self):
        self.url = "https://acme.atlassian.net"
        self._pages = [
            {"total": 3, "issues": [
                {"key": "B-1", "fields": {"summary": "s1", "description": "d1",
                 "issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
                {"key": "B-2", "fields": {"summary": "s2", "description": "d2",
                 "issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
            ]},
            {"total": 3, "issues": [
                {"key": "B-3", "fields": {"summary": "s3", "description": "d3",
                 "issuetype": {"name": "Bug"}, "status": {"name": "Done"}}},
            ]},
        ]

    def jql(self, jql, start=0, limit=50, fields=None):
        idx = 0 if start == 0 else 1
        return self._pages[idx]


def _client_with(fake):
    c = JiraApiClient.__new__(JiraApiClient)
    c._jira = fake
    return c


def test_fetch_bugs_paginates():
    c = _client_with(_FakeJira())
    bugs = c.fetch_bugs("issuetype = Bug", page_size=2)
    assert [b.key for b in bugs] == ["B-1", "B-2", "B-3"]
    assert bugs[0].url == "https://acme.atlassian.net/browse/B-1"


def test_fetch_bugs_respects_max_issues():
    c = _client_with(_FakeJira())
    bugs = c.fetch_bugs("issuetype = Bug", page_size=2, max_issues=1)
    assert len(bugs) == 1


def test_fetch_bugs_wraps_errors():
    class _Boom:
        url = "https://acme.atlassian.net"
        def jql(self, *a, **k):
            raise RuntimeError("401 Unauthorized")
    c = _client_with(_Boom())
    with pytest.raises(JiraApiError):
        c.fetch_bugs("issuetype = Bug")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.client'`

- [ ] **Step 3: Write the implementation** — create `src/jira/client.py`:

```python
from typing import List

from atlassian import Jira

from src.jira.models import JiraBug, adf_to_text


class JiraApiError(Exception):
    """Error al hablar con la API de Jira (red, auth, etc.)."""


class JiraApiClient:
    def __init__(self, base_url: str, email: str, token: str):
        self._jira = Jira(url=base_url, username=email, password=token, cloud=True)

    def fetch_bugs(self, jql: str, *, page_size: int = 50, max_issues: int = 1000) -> List[JiraBug]:
        bugs: List[JiraBug] = []
        start = 0
        base = self._jira.url.rstrip("/")
        try:
            while len(bugs) < max_issues:
                result = self._jira.jql(
                    jql, start=start, limit=page_size,
                    fields="summary,description,issuetype,status",
                )
                issues = result.get("issues") or []
                if not issues:
                    break
                for issue in issues:
                    fields = issue.get("fields") or {}
                    bugs.append(JiraBug(
                        key=issue.get("key") or "",
                        summary=(fields.get("summary") or "").strip(),
                        description=adf_to_text(fields.get("description")),
                        issue_type=(fields.get("issuetype") or {}).get("name") or "",
                        status=(fields.get("status") or {}).get("name") or "",
                        url=f"{base}/browse/{issue.get('key')}",
                    ))
                    if len(bugs) >= max_issues:
                        break
                start += len(issues)
                if start >= (result.get("total") or 0):
                    break
        except Exception as exc:  # noqa: BLE001 — envolvemos cualquier fallo de la librería
            raise JiraApiError(str(exc)) from exc
        return bugs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/client.py tests/test_jira_client.py
git commit -m "feat: cliente de la API de Jira (JQL + paginación + JiraApiError)"
```

---

### Task 8: Extender `IngestItem` + persistir `external_ref`/`external_url` + `existing_external_refs`

**Files:**
- Modify: `src/defects/repository.py`
- Test: `tests/test_ingest_item_external.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_ingest_item_external.py`:

```python
from src.defects.repository import IngestItem
from src.ingest.models import FailureRecord


def _rec():
    return FailureRecord(test_name="t", error_type="Bug", message="m", trace=None,
                         project="p", source="jira")


def test_ingest_item_external_fields_default_none():
    item = IngestItem(rec=_rec(), fingerprint="fp", embedding=[0.0] * 384)
    assert item.external_ref is None
    assert item.external_url is None


def test_ingest_item_accepts_external_fields():
    item = IngestItem(rec=_rec(), fingerprint="fp", embedding=[0.0] * 384,
                      external_ref="PROJ-1", external_url="https://x/browse/PROJ-1")
    assert item.external_ref == "PROJ-1"
    assert item.external_url == "https://x/browse/PROJ-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingest_item_external.py -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'external_ref'`

- [ ] **Step 3: Update `IngestItem` and the failures insert.**

(a) In `src/defects/repository.py`, ensure `Optional` is imported (`from typing import Any, Dict, List, Optional, Sequence`) and change the dataclass:

```python
@dataclass
class IngestItem:
    rec: FailureRecord
    fingerprint: str
    embedding: Sequence[float]
    external_ref: Optional[str] = None
    external_url: Optional[str] = None
```

(b) In `ingest_run`, the `insert into public.failures` statement: add the two columns and two params. Replace the existing insert with:

```python
                    cur.execute(
                        """
                        insert into public.failures
                            (run_id, org_id, test_name, error_type, message, trace,
                             fingerprint, embedding, sanitized, defect_family_id,
                             external_ref, external_url)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s)
                        """,
                        (
                            run_id,
                            org_id,
                            item.rec.test_name,
                            item.rec.error_type,
                            item.rec.message,
                            item.rec.trace,
                            item.fingerprint,
                            Vector(list(item.embedding)),
                            family_id,
                            item.external_ref,
                            item.external_url,
                        ),
                    )
```

(c) Add a new method to `AssuranceRepository` (after `ingest_run`) to list already-imported external refs for dedup:

```python
    def existing_external_refs(self, *, user_id: str, org_id: str) -> List[str]:
        """Return the set of external_ref values already present for the org's failures."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select distinct external_ref from public.failures"
                    " where org_id = %s and external_ref is not null"
                    " and exists (select 1 from public.memberships m"
                    "             where m.org_id = %s and m.user_id = %s)",
                    (org_id, org_id, user_id),
                )
                return [r["external_ref"] for r in cur.fetchall()]
```

- [ ] **Step 4: Run the unit test (the new fields)**

Run: `python3 -m pytest tests/test_ingest_item_external.py -v`
Expected: PASS (2 passed). NOTE: the failures-insert and `existing_external_refs` changes are exercised by the integration test in Task 14; this unit test only locks the dataclass shape.

- [ ] **Step 5: Run the full unit suite to confirm no regressions**

Run: `python3 -m pytest -m "not integration" -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/defects/repository.py tests/test_ingest_item_external.py
git commit -m "feat: external_ref/external_url en IngestItem + failures + existing_external_refs"
```

---

### Task 9: Migración 005 (CHECK source, columnas, `org_integrations`)

**Files:**
- Create: `db/migrations/005_jira_integration.sql`

- [ ] **Step 1: Write the migration** — create `db/migrations/005_jira_integration.sql`:

```sql
-- db/migrations/005_jira_integration.sql
-- Integra bugs de Jira en el Defect DNA: amplía source, añade trazabilidad y
-- guarda las credenciales por org (token cifrado en capa de app).
alter table public.test_runs drop constraint test_runs_source_check;
alter table public.test_runs add constraint test_runs_source_check
    check (source in ('allure', 'junit', 'testng', 'cucumber', 'playwright', 'cypress', 'robot', 'jira'));

alter table public.failures add column if not exists external_ref text;
alter table public.failures add column if not exists external_url text;

create table if not exists public.org_integrations (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    provider text not null check (provider in ('jira')),
    base_url text not null,
    email text not null,
    api_token_enc text not null,
    jql text not null default 'issuetype = Bug',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, provider)
);
create index if not exists idx_org_integrations_org on public.org_integrations (org_id);
```

- [ ] **Step 2: Apply the migration to Supabase**

Run:
```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg
sql = open('db/migrations/005_jira_integration.sql').read()
with psycopg.connect(os.getenv('DATABASE_URL','')) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute('select pg_get_constraintdef(oid) from pg_constraint where conname=%s', ('test_runs_source_check',))
        print('source check:', cur.fetchone()[0])
        cur.execute(\"select count(*) from information_schema.columns where table_name='failures' and column_name in ('external_ref','external_url')\")
        print('failures new cols:', cur.fetchone()[0])
        cur.execute(\"select to_regclass('public.org_integrations')\")
        print('org_integrations:', cur.fetchone()[0])
    conn.commit()
"
```
Expected: source check lists 8 sources incl. `jira`; `failures new cols: 2`; `org_integrations: org_integrations`.

- [ ] **Step 3: Commit**

```bash
git add db/migrations/005_jira_integration.sql
git commit -m "feat: migración 005 (source=jira, external_ref/url, org_integrations)"
```

---

### Task 10: `IntegrationsRepository`

**Files:**
- Create: `src/jira/integrations_repository.py`
- Test: `tests/test_integrations_repository.py` (integration)

- [ ] **Step 1: Write the failing test** — create `tests/test_integrations_repository.py`:

```python
import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from cryptography.fernet import Fernet  # noqa: E402
import psycopg  # noqa: E402

from src.jira.integrations_repository import IntegrationsRepository  # noqa: E402

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def repo(monkeypatch):
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    monkeypatch.setenv("MNEMO_SECRET_KEY", Fernet.generate_key().decode())
    return IntegrationsRepository(DBURL)


@pytest.fixture
def org():
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"int-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s, %s) returning id",
                        ("int-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def test_upsert_then_get_config_hides_token(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.upsert_jira_config(user_id=u, org_id=o, base_url="https://acme.atlassian.net",
                            email="a@b.c", token="secret-token", jql="issuetype = Bug")
    cfg = repo.get_jira_config(user_id=u, org_id=o)
    assert cfg["configured"] is True
    assert cfg["base_url"] == "https://acme.atlassian.net"
    assert "token" not in cfg  # nunca se devuelve el token


def test_get_credentials_decrypts(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.upsert_jira_config(user_id=u, org_id=o, base_url="https://acme.atlassian.net",
                            email="a@b.c", token="secret-token", jql="issuetype = Bug")
    creds = repo.get_jira_credentials(user_id=u, org_id=o)
    assert creds["token"] == "secret-token"


def test_non_member_rejected(repo, org):
    other = str(uuid.uuid4())
    with pytest.raises(PermissionError):
        repo.upsert_jira_config(user_id=other, org_id=org["org_id"], base_url="https://acme.atlassian.net",
                                email="a@b.c", token="t", jql="issuetype = Bug")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_integrations_repository.py -m integration -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.integrations_repository'`

- [ ] **Step 3: Write the implementation** — create `src/jira/integrations_repository.py`:

```python
from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row

from src.config import DATABASE_URL
from src.jira.crypto import decrypt_token, encrypt_token


class IntegrationsRepository:
    """Credenciales de integraciones por org. El pooler bypassa RLS, así que el
    aislamiento es por membership en cada consulta. El token va cifrado (Fernet)."""

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.db_url, row_factory=dict_row)

    def _require_member(self, cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s) as ok",
            (org_id, user_id),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("user is not a member of the organization")

    def upsert_jira_config(self, *, user_id: str, org_id: str, base_url: str,
                           email: str, token: str, jql: str) -> None:
        enc = encrypt_token(token)
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    """
                    insert into public.org_integrations
                        (org_id, provider, base_url, email, api_token_enc, jql)
                    values (%s, 'jira', %s, %s, %s, %s)
                    on conflict (org_id, provider) do update
                       set base_url = excluded.base_url,
                           email = excluded.email,
                           api_token_enc = excluded.api_token_enc,
                           jql = excluded.jql,
                           updated_at = now()
                    """,
                    (org_id, base_url, email, enc, jql),
                )
            conn.commit()

    def get_jira_config(self, *, user_id: str, org_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select base_url, email, jql from public.org_integrations"
                    " where org_id = %s and provider = 'jira'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return {"configured": False, "base_url": None, "email": None, "jql": None}
        return {"configured": True, "base_url": row["base_url"],
                "email": row["email"], "jql": row["jql"]}

    def get_jira_credentials(self, *, user_id: str, org_id: str) -> Optional[Dict[str, str]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select base_url, email, api_token_enc, jql"
                    " from public.org_integrations where org_id = %s and provider = 'jira'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"base_url": row["base_url"], "email": row["email"],
                "token": decrypt_token(row["api_token_enc"]), "jql": row["jql"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_integrations_repository.py -m integration -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/integrations_repository.py tests/test_integrations_repository.py
git commit -m "feat: IntegrationsRepository (config Jira cifrada por org)"
```

---

### Task 11: `JiraIngestionService`

**Files:**
- Create: `src/jira/ingestion_service.py`
- Test: `tests/test_jira_ingestion_service.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_jira_ingestion_service.py`:

```python
import pytest

from src.jira.ingestion_service import JiraIngestionService
from src.jira.models import JiraBug


class _FakeEmbedder:
    def embed(self, text):
        return [0.1] * 384


class _FakeRepo:
    def __init__(self, existing=None):
        self._existing = existing or []
        self.captured = None

    def existing_external_refs(self, *, user_id, org_id):
        return list(self._existing)

    def ingest_run(self, *, user_id, org_id, project, source, items):
        self.captured = {"source": source, "items": items}
        return {"run_id": "r", "ingested": len(items), "known": 0, "novel": len(items)}


class _FakeIntegrations:
    def __init__(self, creds):
        self._creds = creds

    def get_jira_credentials(self, *, user_id, org_id):
        return self._creds


def _bug(key):
    return JiraBug(key=key, summary="Login timeout", description="waited 30s",
                   issue_type="Bug", status="Open", url=f"https://x/browse/{key}")


def test_ingest_bugs_sets_source_and_external_ref():
    repo = _FakeRepo()
    svc = JiraIngestionService(repo=repo, embedder=_FakeEmbedder(),
                               integrations=_FakeIntegrations(None))
    out = svc.ingest_bugs(user_id="u", org_id="o", project="p", bugs=[_bug("B-1")])
    assert repo.captured["source"] == "jira"
    item = repo.captured["items"][0]
    assert item.external_ref == "B-1"
    assert item.external_url == "https://x/browse/B-1"
    assert out["skipped"] == 0


def test_ingest_bugs_dedups_existing():
    repo = _FakeRepo(existing=["B-1"])
    svc = JiraIngestionService(repo=repo, embedder=_FakeEmbedder(),
                               integrations=_FakeIntegrations(None))
    out = svc.ingest_bugs(user_id="u", org_id="o", project="p", bugs=[_bug("B-1"), _bug("B-2")])
    assert out["skipped"] == 1
    assert len(repo.captured["items"]) == 1
    assert repo.captured["items"][0].external_ref == "B-2"


def test_ingest_from_pull_without_config_raises():
    repo = _FakeRepo()
    svc = JiraIngestionService(repo=repo, embedder=_FakeEmbedder(),
                               integrations=_FakeIntegrations(None))
    with pytest.raises(ValueError):
        svc.ingest_from_pull(user_id="u", org_id="o", project="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_jira_ingestion_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.jira.ingestion_service'`

- [ ] **Step 3: Write the implementation** — create `src/jira/ingestion_service.py`:

```python
from dataclasses import replace
from typing import Any, Dict, List, Set

from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.jira.client import JiraApiClient
from src.jira.export import parse_jira_export
from src.jira.integrations_repository import IntegrationsRepository
from src.jira.mapper import bug_to_record
from src.jira.models import JiraBug
from src.jira.safe_url import validate_base_url
from src.sanitizer import sanitize_text


class JiraIngestionService:
    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder,
                 integrations: IntegrationsRepository):
        self.repo = repo
        self.embedder = embedder
        self.integrations = integrations

    def _to_items(self, bugs: List[JiraBug], *, project: str, seen: Set[str]) -> List[IngestItem]:
        items: List[IngestItem] = []
        for bug in bugs:
            if not bug.key or bug.key in seen:
                continue
            seen.add(bug.key)
            rec = bug_to_record(bug, project=project)
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            emb = self.embedder.embed(f"{bug.summary} {bug.description}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=emb,
                                    external_ref=bug.key, external_url=bug.url or None))
        return items

    def ingest_bugs(self, *, user_id: str, org_id: str, project: str,
                    bugs: List[JiraBug]) -> Dict[str, Any]:
        existing = self.repo.existing_external_refs(user_id=user_id, org_id=org_id)
        items = self._to_items(bugs, project=project, seen=set(existing))
        skipped = len(bugs) - len(items)
        if not items:
            return {"run_id": None, "ingested": 0, "known": 0, "novel": 0, "skipped": skipped}
        result = self.repo.ingest_run(user_id=user_id, org_id=org_id, project=project,
                                      source="jira", items=items)
        result["skipped"] = skipped
        return result

    def ingest_from_export(self, *, user_id: str, org_id: str, project: str,
                           data: bytes) -> Dict[str, Any]:
        bugs = parse_jira_export(data)
        return self.ingest_bugs(user_id=user_id, org_id=org_id, project=project, bugs=bugs)

    def ingest_from_pull(self, *, user_id: str, org_id: str, project: str) -> Dict[str, Any]:
        creds = self.integrations.get_jira_credentials(user_id=user_id, org_id=org_id)
        if creds is None:
            raise ValueError("configura la integración de Jira primero")
        validate_base_url(creds["base_url"])
        client = JiraApiClient(creds["base_url"], creds["email"], creds["token"])
        bugs = client.fetch_bugs(creds["jql"])
        return self.ingest_bugs(user_id=user_id, org_id=org_id, project=project, bugs=bugs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_jira_ingestion_service.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/jira/ingestion_service.py tests/test_jira_ingestion_service.py
git commit -m "feat: JiraIngestionService (export + pull, dedup por external_ref)"
```

---

### Task 12: Modelos Pydantic + endpoints

**Files:**
- Modify: `src/multitenant_models.py` (append models)
- Modify: `src/api_v2.py` (lazy deps + 4 endpoints)
- Test: `tests/test_api_v2_jira.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_api_v2_jira.py`:

```python
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.api_v2 import router, get_current_user, get_jira_ingestion_service, get_integrations_repo
from fastapi import FastAPI


class _User:
    user_id = "u1"


class _FakeIntegrations:
    def __init__(self):
        self.saved = None

    def upsert_jira_config(self, **kw):
        self.saved = kw

    def get_jira_config(self, *, user_id, org_id):
        return {"configured": True, "base_url": "https://acme.atlassian.net",
                "email": "a@b.c", "jql": "issuetype = Bug"}


class _FakeService:
    def ingest_from_pull(self, *, user_id, org_id, project):
        return {"run_id": "r", "ingested": 2, "known": 0, "novel": 2, "skipped": 1}


def _app(integrations, service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[get_integrations_repo] = lambda: integrations
    app.dependency_overrides[get_jira_ingestion_service] = lambda: service
    return TestClient(app)


def test_get_jira_config_omits_token():
    client = _app(_FakeIntegrations(), _FakeService())
    r = client.get("/v2/integrations/jira", params={"org_id": "o1"})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert "token" not in body


def test_set_jira_config_rejects_http():
    integrations = _FakeIntegrations()
    client = _app(integrations, _FakeService())
    r = client.post("/v2/integrations/jira", json={
        "org_id": "o1", "base_url": "http://acme.atlassian.net",
        "email": "a@b.c", "token": "t", "jql": "issuetype = Bug"})
    assert r.status_code == 400
    assert integrations.saved is None


def test_pull_returns_counts():
    client = _app(_FakeIntegrations(), _FakeService())
    r = client.post("/v2/ingest/jira/pull", json={"org_id": "o1", "project": "p"})
    assert r.status_code == 200
    assert r.json()["skipped"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v2_jira.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_jira_ingestion_service'`

- [ ] **Step 3: Add the Pydantic models** — append to `src/multitenant_models.py`:

```python
class JiraConfigRequest(BaseModel):
    org_id: str
    base_url: str
    email: str
    token: str
    jql: str = "issuetype = Bug"


class JiraConfigResponse(BaseModel):
    configured: bool
    base_url: Optional[str] = None
    email: Optional[str] = None
    jql: Optional[str] = None


class JiraPullRequest(BaseModel):
    org_id: str
    project: str


class JiraIngestResponse(BaseModel):
    run_id: Optional[str] = None
    ingested: int
    known: int
    novel: int
    skipped: int
```

(If `Optional` is not already imported in that file, add `from typing import Optional`.)

- [ ] **Step 4: Add lazy deps + endpoints** — in `src/api_v2.py`:

(a) Add imports near the existing imports:

```python
from src.jira.client import JiraApiError
from src.jira.integrations_repository import IntegrationsRepository
from src.jira.ingestion_service import JiraIngestionService
from src.jira.safe_url import validate_base_url
from src.multitenant_models import (
    JiraConfigRequest, JiraConfigResponse, JiraPullRequest, JiraIngestResponse,
)
```

(b) Add lazy singletons next to the existing `get_ingestion_service` (follow that exact pattern):

```python
_integrations_repo = None
_jira_service = None


def get_integrations_repo() -> IntegrationsRepository:
    global _integrations_repo
    if _integrations_repo is None:
        _integrations_repo = IntegrationsRepository()
    return _integrations_repo


def get_jira_ingestion_service() -> JiraIngestionService:
    global _jira_service
    if _jira_service is None:
        from src.defects.embedder import LocalEmbedder
        _jira_service = JiraIngestionService(
            repo=get_assurance_repo(), embedder=LocalEmbedder(),
            integrations=get_integrations_repo(),
        )
    return _jira_service
```

(c) Add the four endpoints (after the existing `/ingest/report` endpoint):

```python
@router.post("/integrations/jira", response_model=JiraConfigResponse)
def set_jira_integration(
    body: JiraConfigRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> JiraConfigResponse:
    try:
        base = validate_base_url(body.base_url)
        integrations.upsert_jira_config(
            user_id=user.user_id, org_id=body.org_id, base_url=base,
            email=body.email, token=body.token, jql=body.jql,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraConfigResponse(configured=True, base_url=base, email=body.email, jql=body.jql)


@router.get("/integrations/jira", response_model=JiraConfigResponse)
def get_jira_integration(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> JiraConfigResponse:
    try:
        cfg = integrations.get_jira_config(user_id=user.user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraConfigResponse(**cfg)


@router.post("/ingest/jira/file", response_model=JiraIngestResponse)
def ingest_jira_file(
    file: UploadFile = File(...),
    project: str = Form(...),
    org_id: str = Form(...),
    user: AuthenticatedUser = Depends(get_current_user),
    service: JiraIngestionService = Depends(get_jira_ingestion_service),
) -> JiraIngestResponse:
    try:
        data = file.file.read()
        result = service.ingest_from_export(
            user_id=user.user_id, org_id=org_id, project=project, data=data)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraIngestResponse(**result)


@router.post("/ingest/jira/pull", response_model=JiraIngestResponse)
def ingest_jira_pull(
    body: JiraPullRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: JiraIngestionService = Depends(get_jira_ingestion_service),
) -> JiraIngestResponse:
    try:
        result = service.ingest_from_pull(
            user_id=user.user_id, org_id=body.org_id, project=body.project)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status_code=502, detail=f"Jira API error: {exc}") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return JiraIngestResponse(**result)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_v2_jira.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full unit suite**

Run: `python3 -m pytest -m "not integration" -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/multitenant_models.py src/api_v2.py tests/test_api_v2_jira.py
git commit -m "feat: endpoints /v2/integrations/jira y /v2/ingest/jira/{file,pull}"
```

---

### Task 13: Frontend — página de Integraciones

**Files:**
- Modify: `frontend/src/lib/api/types.ts` (append Jira types)
- Modify: `frontend/src/lib/api/endpoints.ts` (append client fns)
- Create: `frontend/src/app/app/integrations/page.tsx`

- [ ] **Step 1: Add TS types** — append to `frontend/src/lib/api/types.ts`:

```typescript
export interface JiraConfigResponse {
  configured: boolean;
  base_url: string | null;
  email: string | null;
  jql: string | null;
}

export interface JiraIngestResponse {
  run_id: string | null;
  ingested: number;
  known: number;
  novel: number;
  skipped: number;
}
```

- [ ] **Step 2: Add client functions** — append to `frontend/src/lib/api/endpoints.ts` (follow the existing `ingestReport`/`getDefects` style; reuse the same base path + auth header helper already used there):

```typescript
export async function getJiraConfig(token: string, orgId: string): Promise<JiraConfigResponse> {
  return apiGet<JiraConfigResponse>(`/v2/integrations/jira?org_id=${encodeURIComponent(orgId)}`, token);
}

export async function saveJiraConfig(
  token: string,
  body: { org_id: string; base_url: string; email: string; token: string; jql: string },
): Promise<JiraConfigResponse> {
  return apiPostJson<JiraConfigResponse>(`/v2/integrations/jira`, body, token);
}

export async function pullJiraBugs(
  token: string,
  body: { org_id: string; project: string },
): Promise<JiraIngestResponse> {
  return apiPostJson<JiraIngestResponse>(`/v2/ingest/jira/pull`, body, token);
}

export async function ingestJiraFile(token: string, form: FormData): Promise<JiraIngestResponse> {
  return apiPostForm<JiraIngestResponse>(`/v2/ingest/jira/file`, form, token);
}
```

NOTE: use the SAME helper names that already exist in `endpoints.ts` (e.g. the file currently has functions for GET/POST-JSON/POST-FormData and a `JiraConfigResponse`/`JiraIngestResponse` import). If the existing helpers are named differently (e.g. `apiFetch`), adapt these four functions to call them exactly as the existing `ingestReport`/`getDefects` do — read the file first and mirror its conventions. Import the two new types at the top.

- [ ] **Step 3: Create the page** — create `frontend/src/app/app/integrations/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getOrganizations, getJiraConfig, saveJiraConfig, pullJiraBugs, ingestJiraFile } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function IntegrationsPage() {
  const { accessToken } = useAuth();
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [jql, setJql] = useState("issuetype = Bug");
  const [project, setProject] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgId = orgsQuery.data?.[0]?.id ?? "";

  const configQuery = useQuery({
    queryKey: ["jira-config", orgId],
    queryFn: () => getJiraConfig(accessToken!, orgId),
    enabled: Boolean(accessToken && orgId),
  });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setMsg(null); setBusy(true);
    try {
      await saveJiraConfig(accessToken!, { org_id: orgId, base_url: baseUrl, email, token, jql });
      setMsg("Configuración de Jira guardada.");
      setToken("");
      void configQuery.refetch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar la configuración.");
    } finally { setBusy(false); }
  }

  async function pull() {
    setError(null); setMsg(null); setBusy(true);
    try {
      const r = await pullJiraBugs(accessToken!, { org_id: orgId, project: project || "jira" });
      setMsg(`Importados ${r.ingested} (nuevos ${r.novel}, conocidos ${r.known}, omitidos ${r.skipped}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al importar desde Jira.");
    } finally { setBusy(false); }
  }

  async function upload() {
    if (!file) { setError("Selecciona un archivo de export."); return; }
    setError(null); setMsg(null); setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("project", project || "jira");
      form.append("org_id", orgId);
      const r = await ingestJiraFile(accessToken!, form);
      setMsg(`Importados ${r.ingested} (nuevos ${r.novel}, conocidos ${r.known}, omitidos ${r.skipped}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir el export.");
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Integraciones</h1>
        <p className="text-sm text-zinc-500">Conecta Jira para traer bugs al Defect DNA.</p>
      </div>

      <Card className="max-w-xl space-y-4 p-5">
        <form onSubmit={save} className="space-y-3">
          <div className="space-y-1"><Label htmlFor="ju">Base URL</Label>
            <Input id="ju" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://acme.atlassian.net" /></div>
          <div className="space-y-1"><Label htmlFor="je">Email</Label>
            <Input id="je" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tu@empresa.com" /></div>
          <div className="space-y-1"><Label htmlFor="jt">API token</Label>
            <Input id="jt" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={configQuery.data?.configured ? "•••• (ya configurado)" : ""} /></div>
          <div className="space-y-1"><Label htmlFor="jq">JQL</Label>
            <Input id="jq" value={jql} onChange={(e) => setJql(e.target.value)} /></div>
          <Button type="submit" disabled={busy || !orgId}>Guardar configuración</Button>
        </form>
      </Card>

      <Card className="max-w-xl space-y-3 p-5">
        <div className="space-y-1"><Label htmlFor="jp">Proyecto Mnemo</Label>
          <Input id="jp" value={project} onChange={(e) => setProject(e.target.value)} placeholder="jira" /></div>
        <div className="flex gap-3">
          <Button onClick={pull} disabled={busy || !orgId || !configQuery.data?.configured}>Importar bugs ahora (API)</Button>
        </div>
        <div className="space-y-1"><Label htmlFor="jf">…o subir un export</Label>
          <Input id="jf" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
        <Button onClick={upload} disabled={busy || !orgId}>Subir export</Button>
        {msg && <p className="text-sm text-green-700">{msg}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Verify typecheck and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors. (Do NOT run `npm run build` — it hangs in this environment.)

If tsc reports mismatched helper names in `endpoints.ts`, fix the four new functions to use the existing helpers (read the file and mirror `ingestReport`/`getDefects`), then re-run.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/types.ts frontend/src/lib/api/endpoints.ts frontend/src/app/app/integrations/page.tsx
git commit -m "feat: página de Integraciones (config Jira + importar bugs)"
```

---

### Task 14: Verificación e2e backend

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest -m "not integration" -q`
Expected: all green (the prior suite + the new Jira unit tests: models, export, mapper, safe_url, crypto, client, ingest_item_external, jira_ingestion_service, api_v2_jira).

- [ ] **Step 2: Run the new integration test (requires `DATABASE_URL` + `MNEMO_SECRET_KEY`)**

Run: `MNEMO_SECRET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") python3 -m pytest tests/test_integrations_repository.py -m integration -v`
Expected: 3 passed.

- [ ] **Step 3: Smoke-test an export ingest end-to-end (integration)**

Add a temporary check (or run interactively) that a Jira JSON export ingests into a defect family with `external_ref` populated. Use the existing org fixture pattern from `tests/test_assurance_repository.py`. If the environment is too slow for live DB, note it and rely on the unit tests + the Task 10 integration test which already exercises the credentials path.

---

## Notas de implementación

- **TDD estricto**: cada componente RED → GREEN → commit. El plan da el código exacto; el implementador no debe improvisar.
- **Indentación 4 espacios, nunca tabs** (Python). El frontend evita `npm run build` (se cuelga en este entorno): solo `tsc --noEmit` + `lint`.
- **Orden**: Task 1 (cryptography) antes de Task 6 (crypto) y 10/11. Tasks 2-7 son módulos independientes. Task 8 antes de 11 (usa `IngestItem.external_ref` + `existing_external_refs`). Task 9 (migración) antes de 10 y 14 (integración). 12 después de 10+11. 13 después de 12.
- **Seguridad**: el token NUNCA se devuelve en GET ni se loguea; `validate_base_url` se aplica al guardar y antes de cada pull; `MNEMO_SECRET_KEY` debe estar en `.env` (genera una con `Fernet.generate_key()`).
- **`endpoints.ts`**: los nombres de helper (`apiGet`/`apiPostJson`/`apiPostForm`) son orientativos — el implementador DEBE leer el archivo y usar los helpers reales que ya emplean `ingestReport`/`getDefects`.

