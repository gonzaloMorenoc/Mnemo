# Mnemo Autopilot — F1: Cimientos de ingesta viva (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el CI del cliente pueda POSTear (autenticado por HMAC) un artefacto de run de Playwright enriquecido, y Mnemo persista resultados por test (pass+fail con commit SHA y estado de retry) y snapshots DOM, mientras ingiere los fallos en el Defect DNA existente.

**Architecture:** Un endpoint `POST /v2/ci/webhook` verifica HMAC sobre el cuerpo crudo, valida el artefacto (Pydantic), y delega en un `CiIngestionService` que reutiliza el pipeline existente (sanitize→fingerprint→embed→`ingest_run`) para los fallos y añade `record_test_results` + `save_dom_snapshots`. Sin usuario humano: la ingesta se atribuye a una cuenta de servicio (`CI_SERVICE_USER_ID`) miembro del org, así los chequeos de membership existentes siguen aplicando sin cambios.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, psycopg (dict_row), pgvector, Postgres (Supabase), pytest.

## Global Constraints

- Python 3.13; sin sintaxis que rompa <3.10 en módulos compartidos (el repo evita PEP 604 en `api_v2.py`).
- Aislamiento multitenant: el rol del pooler hace **BYPASS de RLS** → el aislamiento real son los **chequeos de membership en la capa de aplicación**. NUNCA quitarlos. (`src/defects/repository.py:25-31`)
- Inmutabilidad: crear objetos nuevos, no mutar (`dataclasses.replace` como en `ingestion_service.py:57`).
- Tests deben pasar sin BD/Ollama vía mocks: `pytest -m "not integration"`. Los que tocan BD real llevan `pytestmark = pytest.mark.integration` y `pytest.skip` si falta `DATABASE_URL`.
- Embeddings `vector(384)` (coherente con `all-MiniLM-L6-v2`).
- Migraciones numeradas; la siguiente libre es **`007`** (existen 001–006).
- Mapeo de errores HTTP del patrón `/v2`: 401 auth/firma, 403 PermissionError, 400 ValueError/OSError, 422 validación, 502 `psycopg.Error`, 503 no configurado.
- Formato de commit: `<type>: <description>` (feat/chore/test). Atribución desactivada.

---

### Task 1: Migración 007 — `test_runs.commit_sha`, `test_results`, `dom_snapshots`

**Files:**
- Create: `db/migrations/007_autopilot_ingestion.sql`

**Interfaces:**
- Produces: tablas `public.test_results(run_id, org_id, test_name, status, retried, created_at)` y `public.dom_snapshots(org_id, project, test_name, kind, content, commit_sha, created_at)`; columna `public.test_runs.commit_sha text`.

- [ ] **Step 1: Escribir la migración** (calca el formato de `db/migrations/002_assurance.sql`: RLS + `force` + policy con `public.is_org_member` + grants a `authenticated`)

```sql
-- db/migrations/007_autopilot_ingestion.sql
-- Mnemo Autopilot F1: cimientos de ingesta viva.
--   test_runs.commit_sha → atar un run a un commit (señal flaky mismo-SHA en F2)
--   test_results          → resultado por test/run (incluye pass) para intermitencia
--   dom_snapshots         → snapshot DOM por test (último verde / fallo) para self-heal (F3)

alter table public.test_runs add column if not exists commit_sha text;

create table if not exists public.test_results (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    test_name text not null,
    status text not null check (status in ('pass', 'fail', 'flaky', 'skipped')),
    retried boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists public.dom_snapshots (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    project text not null,
    test_name text not null,
    kind text not null check (kind in ('last_green', 'failure')),
    content text not null,
    commit_sha text,
    created_at timestamptz not null default now()
);

create index if not exists idx_test_results_run on public.test_results (run_id);
create index if not exists idx_test_results_org on public.test_results (org_id);
create index if not exists idx_test_results_name on public.test_results (org_id, test_name);
create index if not exists idx_dom_snapshots_lookup
    on public.dom_snapshots (org_id, project, test_name, kind);

alter table public.test_results enable row level security;
alter table public.dom_snapshots enable row level security;
alter table public.test_results force row level security;
alter table public.dom_snapshots force row level security;

drop policy if exists test_results_member on public.test_results;
create policy test_results_member on public.test_results for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

drop policy if exists dom_snapshots_member on public.dom_snapshots;
create policy dom_snapshots_member on public.dom_snapshots for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

grant select, insert, update, delete on public.test_results to authenticated;
grant select, insert, update, delete on public.dom_snapshots to authenticated;
```

- [ ] **Step 2: Aplicar la migración** (Supabase self-hosted local o `DATABASE_URL`)

Run: `psql "$DATABASE_URL" -f db/migrations/007_autopilot_ingestion.sql`
Expected: `ALTER TABLE` / `CREATE TABLE` / `CREATE INDEX` / `CREATE POLICY` / `GRANT` sin errores.

- [ ] **Step 3: Verificar el esquema**

Run: `psql "$DATABASE_URL" -c "\d public.test_results" -c "\d public.dom_snapshots" -c "\d public.test_runs"`
Expected: `test_results` y `dom_snapshots` existen con sus columnas; `test_runs` incluye `commit_sha`.

- [ ] **Step 4: Commit**

```bash
git add db/migrations/007_autopilot_ingestion.sql
git commit -m "feat: migración 007 (test_results, dom_snapshots, test_runs.commit_sha)"
```

---

### Task 2: Config — `CI_WEBHOOK_SECRET` y `CI_SERVICE_USER_ID`

**Files:**
- Modify: `src/config.py` (tras el bloque Supabase auth, ~línea 55)
- Test: `tests/test_config.py` (añadir test)

**Interfaces:**
- Produces: `src.config.CI_WEBHOOK_SECRET: str`, `src.config.CI_SERVICE_USER_ID: str`.

- [ ] **Step 1: Escribir el test de presencia/tipo**

```python
# tests/test_config.py — añadir al final
def test_ci_webhook_config_present():
    import src.config as config
    assert hasattr(config, "CI_WEBHOOK_SECRET")
    assert hasattr(config, "CI_SERVICE_USER_ID")
    assert isinstance(config.CI_WEBHOOK_SECRET, str)
    assert isinstance(config.CI_SERVICE_USER_ID, str)
```

- [ ] **Step 2: Ejecutar el test (falla)**

Run: `pytest tests/test_config.py::test_ci_webhook_config_present -v`
Expected: FAIL con `AttributeError` / `assert hasattr(...)` False.

- [ ] **Step 3: Añadir las constantes de config**

```python
# src/config.py — tras SUPABASE_JWT_SECRET (línea ~55)

# CI webhook (Mnemo Autopilot) — ingesta viva desde el CI del cliente.
# Secreto compartido para verificar la firma HMAC-SHA256 del webhook.
CI_WEBHOOK_SECRET = os.getenv("CI_WEBHOOK_SECRET", "")
# Cuenta de servicio (miembro del org) a la que se atribuye la ingesta del CI.
CI_SERVICE_USER_ID = os.getenv("CI_SERVICE_USER_ID", "")
```

- [ ] **Step 4: Ejecutar el test (pasa)**

Run: `pytest tests/test_config.py::test_ci_webhook_config_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: config CI_WEBHOOK_SECRET y CI_SERVICE_USER_ID"
```

---

### Task 3: Verificación HMAC del webhook (`src/ci/webhook_auth.py`)

**Files:**
- Create: `src/ci/__init__.py` (vacío)
- Create: `src/ci/webhook_auth.py`
- Test: `tests/test_ci_webhook_auth.py`

**Interfaces:**
- Produces: `verify_signature(body: bytes, signature_header: str, secret: str) -> bool` (fail-closed: secreto o cabecera vacíos → False).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_ci_webhook_auth.py
import hashlib
import hmac

from src.ci.webhook_auth import verify_signature


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    body = b'{"a":1}'
    assert verify_signature(body, _sign(body, "s3cr3t"), "s3cr3t") is True


def test_tampered_body_fails():
    sig = _sign(b'{"a":1}', "s3cr3t")
    assert verify_signature(b'{"a":2}', sig, "s3cr3t") is False


def test_wrong_secret_fails():
    body = b'{"a":1}'
    assert verify_signature(body, _sign(body, "other"), "s3cr3t") is False


def test_missing_header_fails():
    assert verify_signature(b"{}", "", "s3cr3t") is False


def test_header_without_prefix_fails():
    body = b"{}"
    digest = hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, digest, "s3cr3t") is False


def test_empty_secret_fails_closed():
    body = b"{}"
    assert verify_signature(body, _sign(body, ""), "") is False
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_webhook_auth.py -v`
Expected: FAIL con `ModuleNotFoundError: src.ci.webhook_auth`.

- [ ] **Step 3: Implementar**

```python
# src/ci/__init__.py  (archivo vacío)
```

```python
# src/ci/webhook_auth.py
import hashlib
import hmac

_PREFIX = "sha256="


def verify_signature(body: bytes, signature_header: str, secret: str) -> bool:
    """Verifica la firma HMAC-SHA256 del cuerpo crudo del webhook (estilo GitHub).

    Fail-closed: si falta el secreto o la cabecera, devuelve False. La comparación
    usa hmac.compare_digest (tiempo constante) para no filtrar la firma esperada.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith(_PREFIX):
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    provided = signature_header[len(_PREFIX):]
    return hmac.compare_digest(expected, provided)
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_ci_webhook_auth.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ci/__init__.py src/ci/webhook_auth.py tests/test_ci_webhook_auth.py
git commit -m "feat: verificación HMAC-SHA256 del webhook de CI"
```

---

### Task 4: Modelos del artefacto enriquecido (`src/ci/models.py`)

**Files:**
- Create: `src/ci/models.py`
- Test: `tests/test_ci_models.py`

**Interfaces:**
- Produces: `CiTestResult(test_name, status, retried, error_type?, message?, trace?, file?, line?, dom?)` y `CiRunArtifact(project, org_id, commit_sha, source="playwright", tests: list[CiTestResult])` (Pydantic v2).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_ci_models.py
import pytest
from pydantic import ValidationError

from src.ci.models import CiRunArtifact, CiTestResult


def _artifact_dict():
    return {
        "project": "demo", "org_id": "org-1", "commit_sha": "abc123",
        "source": "playwright",
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html></html>"},
            {"test_name": "home", "status": "pass"},
        ],
    }


def test_parses_valid_artifact():
    art = CiRunArtifact.model_validate(_artifact_dict())
    assert art.project == "demo" and art.commit_sha == "abc123"
    assert len(art.tests) == 2
    assert art.tests[0].status == "fail" and art.tests[0].retried is False


def test_source_defaults_to_playwright():
    d = _artifact_dict()
    del d["source"]
    assert CiRunArtifact.model_validate(d).source == "playwright"


def test_rejects_bad_status():
    with pytest.raises(ValidationError):
        CiTestResult.model_validate({"test_name": "x", "status": "exploded"})


def test_rejects_missing_required():
    with pytest.raises(ValidationError):
        CiRunArtifact.model_validate({"project": "p", "tests": []})
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_models.py -v`
Expected: FAIL con `ModuleNotFoundError: src.ci.models`.

- [ ] **Step 3: Implementar**

```python
# src/ci/models.py
from typing import List, Literal, Optional

from pydantic import BaseModel


class CiTestResult(BaseModel):
    test_name: str
    status: Literal["pass", "fail", "flaky", "skipped"]
    retried: bool = False
    error_type: Optional[str] = None
    message: Optional[str] = None
    trace: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    dom: Optional[str] = None


class CiRunArtifact(BaseModel):
    project: str
    org_id: str
    commit_sha: str
    source: str = "playwright"
    tests: List[CiTestResult]
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_ci_models.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ci/models.py tests/test_ci_models.py
git commit -m "feat: modelos del artefacto enriquecido de CI (Pydantic)"
```

---

### Task 5: Mapeo artefacto → FailureRecords (`src/ci/mapping.py`)

**Files:**
- Create: `src/ci/mapping.py`
- Test: `tests/test_ci_mapping.py`

**Interfaces:**
- Consumes: `CiRunArtifact` (Task 4); `FailureRecord` + `parse_error_type` (`src/ingest/models.py:26,36`).
- Produces: `to_failure_records(artifact: CiRunArtifact) -> list[FailureRecord]` — solo tests `fail`/`flaky` con `message`; infiere `error_type` cuando falta.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_ci_mapping.py
from src.ci.mapping import to_failure_records
from src.ci.models import CiRunArtifact


def _art(tests):
    return CiRunArtifact.model_validate(
        {"project": "demo", "org_id": "o", "commit_sha": "sha", "tests": tests}
    )


def test_only_failed_and_flaky_become_records():
    art = _art([
        {"test_name": "a", "status": "pass"},
        {"test_name": "b", "status": "skipped"},
        {"test_name": "c", "status": "fail", "message": "AssertionError: nope"},
        {"test_name": "d", "status": "flaky", "message": "TimeoutError: x"},
    ])
    recs = to_failure_records(art)
    assert {r.test_name for r in recs} == {"c", "d"}


def test_excludes_failed_without_message():
    art = _art([{"test_name": "c", "status": "fail"}])
    assert to_failure_records(art) == []


def test_infers_error_type_when_missing():
    art = _art([{"test_name": "c", "status": "fail",
                 "message": "TimeoutError: locator not found"}])
    rec = to_failure_records(art)[0]
    assert rec.error_type == "TimeoutError"
    assert rec.project == "demo" and rec.source == "playwright"


def test_keeps_explicit_error_type():
    art = _art([{"test_name": "c", "status": "fail",
                 "error_type": "CustomError", "message": "boom"}])
    assert to_failure_records(art)[0].error_type == "CustomError"
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_mapping.py -v`
Expected: FAIL con `ModuleNotFoundError: src.ci.mapping`.

- [ ] **Step 3: Implementar**

```python
# src/ci/mapping.py
from typing import List

from src.ci.models import CiRunArtifact
from src.ingest.models import FailureRecord, parse_error_type

_FAILED = {"fail", "flaky"}


def to_failure_records(artifact: CiRunArtifact) -> List[FailureRecord]:
    """Convierte los tests fallidos/flaky con mensaje en FailureRecord[].

    Los pass/skipped y los fallos sin mensaje se excluyen (no alimentan el DNA).
    """
    records: List[FailureRecord] = []
    for t in artifact.tests:
        if t.status not in _FAILED or not t.message:
            continue
        records.append(
            FailureRecord(
                test_name=t.test_name,
                error_type=t.error_type or parse_error_type(t.message),
                message=t.message,
                trace=t.trace,
                project=artifact.project,
                source=artifact.source,
            )
        )
    return records
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_ci_mapping.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ci/mapping.py tests/test_ci_mapping.py
git commit -m "feat: mapeo artefacto de CI a FailureRecords"
```

---

### Task 6: Repositorio — `commit_sha` en run + `record_test_results` + `save_dom_snapshots`

**Files:**
- Modify: `src/defects/repository.py` (firma de `ingest_run` ~línea 95-103 y su INSERT ~127-132; añadir 2 métodos nuevos al final de la clase)
- Test: `tests/test_ci_repository.py` (integration)

**Interfaces:**
- Consumes: patrón `_connect`/`_set_claims` + chequeo de membership (`repository.py:38-55,117-125`).
- Produces:
  - `AssuranceRepository.ingest_run(..., commit_sha: Optional[str] = None)` — persiste `commit_sha` en `test_runs`.
  - `record_test_results(*, user_id, org_id, run_id, results: list[dict]) -> int` (cada dict: `test_name`, `status`, `retried`).
  - `save_dom_snapshots(*, user_id, org_id, project, snapshots: list[dict]) -> int` (cada dict: `test_name`, `kind`, `content`, `commit_sha?`).

- [ ] **Step 1: Escribir los tests (integration)**

```python
# tests/test_ci_repository.py
import os
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord

DBURL = os.getenv("DATABASE_URL", "")


def _emb(seed: float):
    return [seed] + [0.0] * 383


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org(repo):
    user_id = str(uuid.uuid4())
    email = f"test-{user_id[:8]}@test.internal"
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (user_id, email),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("test-org-" + user_id[:8], user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def _failure_item(project, msg, seed):
    rec = FailureRecord(test_name="t", error_type="TimeoutError", message=msg,
                        trace=None, project=project, source="playwright")
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_ingest_run_persists_commit_sha(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="p", source="playwright",
                          items=[_failure_item("p", "TimeoutError x", 1.0)],
                          commit_sha="deadbeef")
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select commit_sha from public.test_runs where id = %s", (out["run_id"],))
            assert cur.fetchone()[0] == "deadbeef"


def test_record_test_results_stores_pass_and_fail(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="p", source="playwright",
                          items=[_failure_item("p", "TimeoutError x", 1.0)], commit_sha="sha")
    n = repo.record_test_results(user_id=u, org_id=o, run_id=out["run_id"], results=[
        {"test_name": "login", "status": "fail", "retried": False},
        {"test_name": "home", "status": "pass", "retried": False},
    ])
    assert n == 2
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_results where run_id = %s"
                        " and status = 'pass'", (out["run_id"],))
            assert cur.fetchone()[0] == 1


def test_record_test_results_rejects_non_member(repo, org):
    out = repo.ingest_run(user_id=org["user_id"], org_id=org["org_id"], project="p",
                          source="playwright",
                          items=[_failure_item("p", "x", 0.3)], commit_sha="s")
    with pytest.raises(PermissionError):
        repo.record_test_results(user_id=str(uuid.uuid4()), org_id=org["org_id"],
                                 run_id=out["run_id"], results=[{"test_name": "t", "status": "pass"}])


def test_save_dom_snapshots_stores_kind(repo, org):
    u, o = org["user_id"], org["org_id"]
    n = repo.save_dom_snapshots(user_id=u, org_id=o, project="p", snapshots=[
        {"test_name": "login", "kind": "failure", "content": "<html></html>", "commit_sha": "s"},
        {"test_name": "home", "kind": "last_green", "content": "<html>ok</html>"},
    ])
    assert n == 2
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.dom_snapshots where org_id = %s"
                        " and kind = 'last_green'", (o,))
            assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_repository.py -v` (con `DATABASE_URL` apuntando a la BD con la migración 007)
Expected: FAIL — `ingest_run() got an unexpected keyword argument 'commit_sha'` / `AttributeError: record_test_results`.

- [ ] **Step 3: Extender `ingest_run` con `commit_sha`**

En `src/defects/repository.py`, cambiar la firma (línea ~95-103):

```python
    def ingest_run(
        self,
        *,
        user_id: str,
        org_id: str,
        project: str,
        source: str,
        items: List[IngestItem],
        commit_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
```

y el INSERT de `test_runs` (línea ~127-132):

```python
                cur.execute(
                    "insert into public.test_runs (org_id, project, source, commit_sha)"
                    " values (%s, %s, %s, %s) returning id",
                    (org_id, project, source, commit_sha),
                )
                run_id = cur.fetchone()["id"]
```

- [ ] **Step 4: Añadir los dos métodos nuevos** (al final de la clase `AssuranceRepository`)

```python
    def record_test_results(
        self, *, user_id: str, org_id: str, run_id: str, results: List[Dict[str, Any]]
    ) -> int:
        """Persiste el resultado por test de un run (incluye pass). Devuelve el nº insertado.

        Lanza PermissionError si el usuario no es miembro del org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                for r in results:
                    cur.execute(
                        "insert into public.test_results"
                        " (run_id, org_id, test_name, status, retried)"
                        " values (%s, %s, %s, %s, %s)",
                        (run_id, org_id, r["test_name"], r["status"], r.get("retried", False)),
                    )
            conn.commit()
        return len(results)

    def save_dom_snapshots(
        self, *, user_id: str, org_id: str, project: str, snapshots: List[Dict[str, Any]]
    ) -> int:
        """Persiste snapshots DOM (kind last_green|failure). Devuelve el nº insertado.

        Lanza PermissionError si el usuario no es miembro del org.
        """
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                for s in snapshots:
                    cur.execute(
                        "insert into public.dom_snapshots"
                        " (org_id, project, test_name, kind, content, commit_sha)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (org_id, project, s["test_name"], s["kind"], s["content"],
                         s.get("commit_sha")),
                    )
            conn.commit()
        return len(snapshots)
```

- [ ] **Step 5: Ejecutar (pasa)**

Run: `pytest tests/test_ci_repository.py -v`
Expected: PASS (4 tests). Verificar que los tests existentes siguen verdes: `pytest tests/test_assurance_repository.py -v`.

- [ ] **Step 6: Commit**

```bash
git add src/defects/repository.py tests/test_ci_repository.py
git commit -m "feat: repo commit_sha en run + record_test_results + save_dom_snapshots"
```

---

### Task 7: Servicio de ingesta de CI (`src/ci/ingestion_service.py`)

**Files:**
- Create: `src/ci/ingestion_service.py`
- Test: `tests/test_ci_ingestion_service.py`

**Interfaces:**
- Consumes: `to_failure_records` (Task 5), `CiRunArtifact` (Task 4), `AssuranceRepository.{ingest_run,record_test_results,save_dom_snapshots}` (Task 6), `Embedder` (`src/defects/embedder.py`), `sanitize_text` (`src/sanitizer.py`), `fingerprint` (`src/defects/fingerprint.py`).
- Produces: `CiIngestionService(*, repo, embedder)` con `ingest_artifact(*, user_id, artifact) -> dict` (claves: `run_id, ingested, known, novel, results_recorded, snapshots_saved`).

- [ ] **Step 1: Escribir los tests (unit, mocks)**

```python
# tests/test_ci_ingestion_service.py
from unittest.mock import MagicMock

from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact


def _artifact():
    return CiRunArtifact.model_validate({
        "project": "demo", "org_id": "org-1", "commit_sha": "abc",
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html>fail</html>"},
            {"test_name": "home", "status": "pass", "dom": "<html>ok</html>"},
            {"test_name": "skip_me", "status": "skipped"},
        ],
    })


def _service():
    repo = MagicMock()
    repo.ingest_run.return_value = {"run_id": "r1", "ingested": 1, "known": 0, "novel": 1}
    repo.record_test_results.return_value = 3
    repo.save_dom_snapshots.return_value = 2
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 384
    return CiIngestionService(repo=repo, embedder=embedder), repo


def test_ingest_run_called_with_commit_sha_and_only_failures():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact())
    _, kwargs = repo.ingest_run.call_args
    assert kwargs["commit_sha"] == "abc"
    assert kwargs["org_id"] == "org-1"
    # Solo el fallo (login) se convierte en item del DNA
    assert len(kwargs["items"]) == 1
    assert kwargs["items"][0].rec.test_name == "login"


def test_records_all_test_results_including_pass_and_skip():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact())
    _, kwargs = repo.record_test_results.call_args
    assert kwargs["run_id"] == "r1"
    assert {r["test_name"] for r in kwargs["results"]} == {"login", "home", "skip_me"}


def test_saves_dom_snapshots_only_for_tests_with_dom():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact())
    _, kwargs = repo.save_dom_snapshots.call_args
    snaps = {s["test_name"]: s["kind"] for s in kwargs["snapshots"]}
    assert snaps == {"login": "failure", "home": "last_green"}


def test_returns_aggregate_counts():
    svc, _ = _service()
    out = svc.ingest_artifact(user_id="svc", artifact=_artifact())
    assert out["run_id"] == "r1" and out["novel"] == 1
    assert out["results_recorded"] == 3 and out["snapshots_saved"] == 2
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_ingestion_service.py -v`
Expected: FAIL con `ModuleNotFoundError: src.ci.ingestion_service`.

- [ ] **Step 3: Implementar** (calca `src/defects/ingestion_service.py:53-63`)

```python
# src/ci/ingestion_service.py
from dataclasses import replace
from typing import Any, Dict

from src.ci.mapping import to_failure_records
from src.ci.models import CiRunArtifact
from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.sanitizer import sanitize_text


class CiIngestionService:
    """Orquesta la ingesta de un artefacto de CI: fallos → Defect DNA, más
    resultados por test y snapshots DOM (cimientos para el triaje de F2/F3)."""

    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder):
        self.repo = repo
        self.embedder = embedder

    def ingest_artifact(self, *, user_id: str, artifact: CiRunArtifact) -> Dict[str, Any]:
        items = []
        for rec in to_failure_records(artifact):
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            embedding = self.embedder.embed(f"{clean.error_type or ''} {message}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=embedding))

        result = self.repo.ingest_run(
            user_id=user_id, org_id=artifact.org_id, project=artifact.project,
            source=artifact.source, items=items, commit_sha=artifact.commit_sha,
        )
        run_id = result["run_id"]

        results = [
            {"test_name": t.test_name, "status": t.status, "retried": t.retried}
            for t in artifact.tests
        ]
        self.repo.record_test_results(
            user_id=user_id, org_id=artifact.org_id, run_id=run_id, results=results,
        )

        snapshots = [
            {
                "test_name": t.test_name,
                "kind": "last_green" if t.status == "pass" else "failure",
                "content": t.dom,
                "commit_sha": artifact.commit_sha,
            }
            for t in artifact.tests
            if t.dom
        ]
        snapshots_saved = 0
        if snapshots:
            snapshots_saved = self.repo.save_dom_snapshots(
                user_id=user_id, org_id=artifact.org_id, project=artifact.project,
                snapshots=snapshots,
            )

        return {
            **result,
            "results_recorded": len(results),
            "snapshots_saved": snapshots_saved,
        }
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_ci_ingestion_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/ci/ingestion_service.py tests/test_ci_ingestion_service.py
git commit -m "feat: CiIngestionService (fallos→DNA + resultados + snapshots)"
```

---

### Task 8: Endpoint `POST /v2/ci/webhook`

**Files:**
- Modify: `src/api_v2.py` (imports cabecera; singleton perezoso tras `_jira_service`; endpoint nuevo)
- Modify: `src/multitenant_models.py` (añadir `CiWebhookResponse`)
- Test: `tests/test_api_v2_ci.py`

**Interfaces:**
- Consumes: `CiIngestionService.ingest_artifact` (Task 7), `verify_signature` (Task 3), `CiRunArtifact` (Task 4), `CI_WEBHOOK_SECRET`/`CI_SERVICE_USER_ID` (Task 2).
- Produces: `POST /v2/ci/webhook` (sin auth de usuario; HMAC) → `CiWebhookResponse`.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_api_v2_ci.py
import hashlib
import hmac
import json
from unittest.mock import MagicMock

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2

SECRET = "testsecret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def make_client(service, monkeypatch):
    monkeypatch.setattr(api_v2, "CI_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(api_v2, "CI_SERVICE_USER_ID", "svc-user")
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_ci_ingestion_service] = lambda: service
    return TestClient(app)


def _body() -> bytes:
    return json.dumps({
        "project": "demo", "org_id": "org-1", "commit_sha": "abc", "source": "playwright",
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html></html>"},
            {"test_name": "home", "status": "pass", "dom": "<html>ok</html>"},
        ],
    }).encode()


def _ok_service():
    service = MagicMock()
    service.ingest_artifact.return_value = {
        "run_id": "r1", "ingested": 1, "known": 0, "novel": 1,
        "results_recorded": 2, "snapshots_saved": 2,
    }
    return service


def test_webhook_valid_signature(monkeypatch):
    service = _ok_service()
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "r1"
    service.ingest_artifact.assert_called_once()


def test_webhook_invalid_signature(monkeypatch):
    service = _ok_service()
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    assert resp.status_code == 401
    service.ingest_artifact.assert_not_called()


def test_webhook_malformed_artifact_is_422(monkeypatch):
    service = _ok_service()
    client = make_client(service, monkeypatch)
    body = b'{"not":"an artifact"}'
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 422


def test_webhook_permission_error_is_403(monkeypatch):
    service = _ok_service()
    service.ingest_artifact.side_effect = PermissionError("not a member")
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 403


def test_webhook_db_error_is_502(monkeypatch):
    service = _ok_service()
    service.ingest_artifact.side_effect = psycopg.OperationalError("db down")
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 502
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_api_v2_ci.py -v`
Expected: FAIL — `AttributeError: module 'src.api_v2' has no attribute 'get_ci_ingestion_service'`.

- [ ] **Step 3: Añadir el modelo de respuesta** en `src/multitenant_models.py` (junto a los demás `BaseModel`)

```python
class CiWebhookResponse(BaseModel):
    run_id: str
    ingested: int
    known: int
    novel: int
    results_recorded: int
    snapshots_saved: int
```

- [ ] **Step 4: Añadir imports y singleton** en `src/api_v2.py`

En la cabecera de imports (tras `from fastapi import ...`, añadir `Request`):

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
```

Tras los imports de `src.*` existentes, añadir:

```python
from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact
from src.ci.webhook_auth import verify_signature
from src.config import CI_SERVICE_USER_ID, CI_WEBHOOK_SECRET
```

Añadir `CiWebhookResponse` a la importación desde `src.multitenant_models`.

Tras `_jira_service = None` (línea ~54), añadir:

```python
_ci_ingestion_service = None
```

Tras `get_jira_ingestion_service` (línea ~124), añadir:

```python
def get_ci_ingestion_service() -> CiIngestionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _ci_ingestion_service
    if _ci_ingestion_service is None:
        from src.defects.embedder import LocalEmbedder
        _ci_ingestion_service = CiIngestionService(
            repo=get_assurance_repo(), embedder=LocalEmbedder()
        )
    return _ci_ingestion_service
```

- [ ] **Step 5: Añadir el endpoint** (tras `ingest_report_v2`, línea ~287)

```python
@router.post("/ci/webhook", response_model=CiWebhookResponse)
async def ci_webhook(
    request: Request,
    service: CiIngestionService = Depends(get_ci_ingestion_service),
) -> CiWebhookResponse:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body, signature, CI_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="invalid signature")
    if not CI_SERVICE_USER_ID:
        raise HTTPException(status_code=503, detail="CI service account not configured")
    try:
        artifact = CiRunArtifact.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid artifact") from exc
    try:
        result = service.ingest_artifact(user_id=CI_SERVICE_USER_ID, artifact=artifact)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return CiWebhookResponse(**result)
```

> Nota: `CI_WEBHOOK_SECRET`/`CI_SERVICE_USER_ID` se importan por nombre para que los tests los sustituyan con `monkeypatch.setattr(api_v2, "CI_WEBHOOK_SECRET", ...)`. La firma HMAC se verifica sobre el **cuerpo crudo** (`await request.body()`), no sobre el JSON re-serializado.

- [ ] **Step 6: Ejecutar (pasa)**

Run: `pytest tests/test_api_v2_ci.py -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Verificar que no se rompió nada**

Run: `pytest -m "not integration" -q`
Expected: toda la suite unitaria verde.

- [ ] **Step 8: Commit**

```bash
git add src/api_v2.py src/multitenant_models.py tests/test_api_v2_ci.py
git commit -m "feat: endpoint POST /v2/ci/webhook (HMAC + ingesta de CI)"
```

---

## Self-Review

**1. Cobertura del spec (slice F1 backend):**
- `test_results` (resultado por test, incl. pass, commit SHA) → Tasks 1, 6, 7. ✓
- `dom_snapshots` (último verde / fallo) → Tasks 1, 6, 7. ✓
- `POST /v2/ci/webhook` con HMAC → Tasks 3, 8. ✓
- `mnemo-playwright-reporter` (npm) → **diferido a F1b** (toolchain JS independiente; ver handoff). El contrato que produce está fijado por `CiRunArtifact` (Task 4), así que F1b implementa contra un objetivo concreto. ✓
- Atribución sin usuario humano (cuenta de servicio) → Task 2 + Task 8. ✓

**2. Placeholders:** ninguno; cada paso de código lleva el código completo y cada comando su salida esperada. ✓

**3. Consistencia de tipos:** `CiRunArtifact`/`CiTestResult` (Task 4) se consumen igual en Tasks 5/7/8; `ingest_run(commit_sha=...)` (Task 6) se llama con ese kwarg en Task 7; las claves del dict de retorno (`results_recorded`, `snapshots_saved`) coinciden entre Task 7 y `CiWebhookResponse` (Task 8). ✓

**Corrección sobre el spec:** el spec nombraba la migración `004_autopilot.sql`; el número real libre es **`007`** (001–006 ya existen). El plan usa `007`. Conviene actualizar la referencia en el spec.

---

## Handoff: F1b (reporter) y siguientes fases

- **F1b — `mnemo-playwright-reporter` (npm):** reporter de Playwright (TS) que, por cada test, emite el JSON `CiRunArtifact` (Task 4): estado pass/fail/flaky/skipped, `retried`, error/selector/file/line, y `dom` (HTML del DOM — verde→baseline, rojo→fallo), más `commit_sha` y `org_id`; firma con HMAC y hace POST a `/v2/ci/webhook`. Plan aparte (toolchain JS, tests con vitest).
- **F2 — el cerebro (triaje):** consume `test_results` (intermitencia mismo-SHA) y `dom_snapshots` (señal "DOM cambió"). Es la siguiente espina.

