# Bloque C · C1 — Seed de demo — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar el sistema demostrable al arrancar: la org de demo con 3 escenarios (flaky/mantenimiento/real) ya triados y certificados, una 2ª org para el aislamiento, y un artefacto fresco reservado para el push en vivo.

**Architecture:** T1 crea las fixtures JSON (CiRunArtifact diseñados para clasificar por reglas deterministas). T2 crea `src/demo/seed.py` que las ingiere + pre-procesa (triaje+cert) y cablea `docker_init`.

**Tech Stack:** Python, pytest, pydantic.

## Global Constraints

- **Determinismo del seed:** los escenarios clasifican por reglas R0–R6 del triaje SIN LLM. Las señales (del engine `src/triage/engine.py`): **R1 flaky** = `retry_passed_in_run or intermittent_same_sha`; **R3 maintenance** = `locator_error and not assertion_failure and has_green_baseline and dom_changed`; **R5 real-novel** = `assertion_failure and novel`.
- **Pre-procesado:** tras ingerir, `TriageService.triage_run` + `CertificateService.generate(created_at=...)`. El **gate se OMITE** (la demo local no tiene GitHub App; la UI mostrará el veredicto del certificado, determinista).
- **Idempotente:** si Org A ya existe, no re-sembrar.
- `CiRunArtifact{project, org_id, commit_sha, source="playwright", run_uid?, tests:[CiTestResult]}`; `CiTestResult{test_name, status: pass|fail|flaky|skipped, retried, error_type?, message?, trace?, file?, line?, dom?}`.
- `DATABASE_URL`=prod (integración con cleanup). `python3 -m pytest`. Commits terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Fixtures de demo (CiRunArtifact JSON)

**Files:** Create `scripts/demo_fixtures/flaky.json`, `maintenance_green.json`, `maintenance_red.json`, `real.json`, `fresh_push.json`; Test `tests/test_demo_fixtures.py`.

**Interfaces:** Produces — 5 JSON files parseable como `CiRunArtifact` (con `org_id` placeholder `"__ORG__"` que el seed reemplazará). Mantenimiento: `maintenance_green` (status pass, dom con `#submit`) + `maintenance_red` (status fail, locator error, dom con `#send`).

- [ ] **Step 1: Read the real signal derivation** — read `src/triage/signals.py` (los campos de `Signals`) and `src/triage/service.py` (cómo se derivan `retry_passed_in_run`/`locator_error`/`assertion_failure`/`has_green_baseline`/`dom_changed`/`is_novel` desde los failures) and `classify_error` (qué `error_type`/`message` cuentan como `locator` vs `assertion` vs `infra`). The fixtures' `error_type`/`message`/`status` must be chosen so the derivation lands on R1/R3/R5. Adjust the example values below to the REAL derivation.

- [ ] **Step 2: Write the failing test** — `tests/test_demo_fixtures.py`:

```python
import json
import pathlib

from src.ci.models import CiRunArtifact

FIX = pathlib.Path("scripts/demo_fixtures")


def _load(name):
    data = json.loads((FIX / name).read_text())
    data["org_id"] = "00000000-0000-0000-0000-000000000000"  # placeholder válido para la validación
    return CiRunArtifact.model_validate(data)


def test_all_fixtures_are_valid_artifacts():
    for name in ("flaky.json", "maintenance_green.json", "maintenance_red.json", "real.json", "fresh_push.json"):
        art = _load(name)
        assert art.tests, f"{name} sin tests"


def test_maintenance_pair_has_doms_and_locator_change():
    green = _load("maintenance_green.json")
    red = _load("maintenance_red.json")
    assert green.tests[0].status == "pass" and green.tests[0].dom and "submit" in green.tests[0].dom
    assert red.tests[0].status == "fail" and red.tests[0].dom and "send" in red.tests[0].dom
    assert green.tests[0].test_name == red.tests[0].test_name   # mismo test → baseline


def test_flaky_and_real_shapes():
    flaky = _load("flaky.json")
    real = _load("real.json")
    assert flaky.tests[0].status == "flaky" or flaky.tests[0].retried   # señal de flaky
    assert real.tests[0].status == "fail" and real.tests[0].error_type  # fallo de aserción
```

- [ ] **Step 3: Run, expect FAIL** — `python3 -m pytest tests/test_demo_fixtures.py -q` (no existen los JSON).

- [ ] **Step 4: Create the fixtures** in `scripts/demo_fixtures/` (adjust `error_type`/`message` to what `classify_error` actually maps, per Step 1):

`flaky.json`:
```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-flaky-001", "source": "playwright",
 "tests": [{"test_name": "test_checkout_flujo", "status": "flaky", "retried": true,
            "error_type": "TimeoutError", "message": "Timeout 30000ms esperando #cart",
            "file": "tests/checkout.spec.ts", "line": 42}]}
```

`maintenance_green.json`:
```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-maint-green", "source": "playwright",
 "tests": [{"test_name": "test_login", "status": "pass",
            "dom": "<form id=\"login\"><input name=\"user\"/><button id=\"submit\">Entrar</button></form>"}]}
```

`maintenance_red.json`:
```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-maint-red", "source": "playwright",
 "tests": [{"test_name": "test_login", "status": "fail",
            "error_type": "NoSuchElementError", "message": "locator no encontrado: #submit",
            "file": "tests/login.spec.ts", "line": 10,
            "dom": "<form id=\"login\"><input name=\"user\"/><button id=\"send\">Entrar</button></form>"}]}
```

`real.json`:
```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-real-001", "source": "playwright",
 "tests": [{"test_name": "test_export_csv", "status": "fail",
            "error_type": "AssertionError", "message": "expected status 200 but got 500",
            "trace": "at ExportService.export (export.ts:88)", "file": "tests/export.spec.ts", "line": 88}]}
```

`fresh_push.json` (reservado para el Acto 1 — un fallo de mantenimiento nuevo, NO procesado por el seed):
```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-fresh-push", "source": "playwright",
 "tests": [{"test_name": "test_perfil", "status": "fail",
            "error_type": "NoSuchElementError", "message": "locator no encontrado: #guardar",
            "file": "tests/perfil.spec.ts", "line": 21,
            "dom": "<form id=\"perfil\"><button id=\"guardar-cambios\">Guardar</button></form>"}]}
```

- [ ] **Step 5: Run, expect PASS** — `python3 -m pytest tests/test_demo_fixtures.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 6: Commit**

```bash
git add scripts/demo_fixtures/ tests/test_demo_fixtures.py
git commit -m "feat(demo): fixtures de los 3 escenarios (flaky/mantenimiento/real) + run fresco

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `src/demo/seed.py` + cableado de `docker_init`

**Files:** Create `src/demo/__init__.py`, `src/demo/seed.py`; Modify `scripts/docker_init.py`; Test `tests/test_demo_seed.py`.

**Interfaces:** Consumes — `CiIngestionService.ingest_artifact(user_id, artifact)`, `TriageService.triage_run(user_id, run_id)`, `CertificateService.generate(user_id, run_id, created_at)`, the fixtures (Task 1). Produces — `seed_demo(*, db_url, demo_user_id) -> Dict[str, Any]` returning `{"org_a", "org_b", "runs", "fresh_artifact_path"}`.

- [ ] **Step 1: Write the failing integration test** — `tests/test_demo_seed.py`:

```python
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.demo.seed import seed_demo

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def demo_user():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                    " values (%s,%s,'authenticated','authenticated',now(),now())",
                    (user, f"demo-{user[:8]}@test.internal"))
        conn.commit()
    yield user
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        # borra las orgs creadas por el seed (created_by = user) → CASCADE; luego el user
        cur.execute("delete from public.organizations where created_by=%s", (user,))
        cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_seed_creates_two_orgs_with_processed_runs(demo_user):
    res = seed_demo(db_url=DBURL, demo_user_id=demo_user)
    assert res["org_a"] and res["org_b"] and res["org_a"] != res["org_b"]
    # Org A: 3+ runs con veredictos de las 3 categorías + certificados
    cats = _verdict_categories(res["org_a"])
    assert {"flaky", "maintenance", "real"} <= cats, f"faltan categorías: {cats}"
    assert _has_certificates(res["org_a"])
    # el run fresco NO está ingerido (su commit no aparece)
    assert not _commit_exists("demo-fresh-push")


def test_seed_is_idempotent(demo_user):
    seed_demo(db_url=DBURL, demo_user_id=demo_user)
    res2 = seed_demo(db_url=DBURL, demo_user_id=demo_user)  # segunda vez no duplica
    assert res2.get("skipped") or _org_count(demo_user) == 2
```

(Implement the small helpers `_verdict_categories(org_id)`, `_has_certificates(org_id)`, `_commit_exists(sha)`, `_org_count(user)` as direct `psycopg` queries against `triage_verdicts`/`certificates`/`test_runs`/`organizations` — read the real column/table names from `db/migrations/002_assurance.sql` and the certificate migration. If `triage_verdicts` stores the category under a different column, adapt.)

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_demo_seed.py -q` (no `seed_demo`).

- [ ] **Step 3: Implement `src/demo/seed.py`.** Read `scripts/docker_init.py` (`_seed`), `src/api_v2.py` (`get_ci_ingestion_service`, `get_triage_service`, `get_certificate_service` — how they're built) and mirror that construction. Sketch:

```python
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict

import psycopg

_FIX = pathlib.Path("scripts/demo_fixtures")


def _load_artifact(name: str, org_id: str):
    from src.ci.models import CiRunArtifact
    data = json.loads((_FIX / name).read_text())
    data["org_id"] = org_id
    return CiRunArtifact.model_validate(data)


def _create_org(cur, name: str, user_id: str) -> str:
    cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                (name, user_id))
    return str(cur.fetchone()[0])


def seed_demo(*, db_url: str, demo_user_id: str) -> Dict[str, Any]:
    """Siembra Org A (3 escenarios pre-procesados) + Org B (aislamiento). Idempotente.
    Devuelve un resumen. NO procesa fresh_push.json."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from public.organizations where created_by=%s and name=%s",
                        (demo_user_id, "Demo MTP"))
            if cur.fetchone():
                return {"skipped": True}
            org_a = _create_org(cur, "Demo MTP", demo_user_id)
            org_b = _create_org(cur, "Cliente Beta", demo_user_id)
        conn.commit()

    from src.defects.embedder import LocalEmbedder
    from src.defects.repository import AssuranceRepository
    from src.ci.ingestion_service import CiIngestionService
    from src.triage.service import TriageService
    from src.certify.service import CertificateService  # construir como en api_v2 (firma, repos)

    repo = AssuranceRepository(db_url)
    ingest = CiIngestionService(repo=repo, embedder=LocalEmbedder())
    triage = TriageService(repo=repo)
    # CertificateService: construir igual que get_certificate_service (cert_repo, clave de firma).

    runs = []
    # Mantenimiento: verde (baseline) ANTES que rojo, para has_green_baseline.
    for name in ("maintenance_green.json", "maintenance_red.json", "flaky.json", "real.json"):
        art = _load_artifact(name, org_a)
        res = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        run_id = res["run_id"]
        triage.triage_run(user_id=demo_user_id, run_id=run_id)
        try:
            CertificateService(...).generate(user_id=demo_user_id, run_id=run_id,
                                             created_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            pass  # cert opcional en seed (p.ej. sin clave de firma); el triaje ya está
        runs.append({"fixture": name, "run_id": run_id})

    # Org B: un par de fallos propios (aislamiento), también pre-procesados.
    for name in ("real.json",):
        art = _load_artifact(name, org_b)
        r = ingest.ingest_artifact(user_id=demo_user_id, artifact=art)
        triage.triage_run(user_id=demo_user_id, run_id=r["run_id"])

    return {"org_a": org_a, "org_b": org_b, "runs": runs,
            "fresh_artifact_path": str(_FIX / "fresh_push.json")}
```

Fill in the `CertificateService` construction by mirroring `get_certificate_service` in `src/api_v2.py` (it needs the cert repo + signing key; if the key is absent in the seed env, the `try/except` lets the seed proceed with triage-only — that's acceptable, the demo container provides the key). Create `src/demo/__init__.py` (empty).

- [ ] **Step 4: Wire `docker_init`** — in `scripts/docker_init.py`, replace the body of `_seed(user_id)` with a call to the module:

```python
def _seed(user_id: str):
    from src.demo.seed import seed_demo
    summary = seed_demo(db_url=DBURL, demo_user_id=user_id)
    print(f"demo sembrada: {summary}")
```

(Keep `main()` unchanged: `_wait_db` → `_apply_migrations` → `_ensure_demo_user` → `_seed`.)

- [ ] **Step 5: Run, expect PASS** — `python3 -m pytest tests/test_demo_seed.py -q` → PASS (needs the DB + the HF embedder; if the embedder download is too slow/unavailable in this env, mark the test to skip gracefully and note it — the binding behavior is the two orgs + the three categories + idempotency). Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 6: Commit**

```bash
git add src/demo/ scripts/docker_init.py tests/test_demo_seed.py
git commit -m "feat(demo): seed_demo — 2 orgs + 3 escenarios pre-procesados, idempotente

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **El run de mantenimiento se siembra verde→rojo** (en ese orden) para que el rojo tenga `has_green_baseline` y `dom_changed` → R3. Si la derivación de `has_green_baseline` mira runs del mismo `project`+`test_name`, el orden basta.
- **El cert es best-effort en el seed** (try/except): si falta la clave de firma en el entorno de test, el triaje ya deja el run clasificado y la idempotencia/orgs se verifican igual; el contenedor de demo sí tendrá la clave.
- **`fresh_push.json` no se procesa** — es la munición del Acto 1 (C4 lo enviará por el webhook en vivo).
- **Fuera de alcance:** C2 (UI: briefing+ROI), C3 (PDF), C4 (guion 3 actos + aislamiento A/B en vivo + ensayo); Bloque D.
