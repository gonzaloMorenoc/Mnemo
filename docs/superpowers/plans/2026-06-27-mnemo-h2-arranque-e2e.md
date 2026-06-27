# H2 — Arranque e2e — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un push arranque el motor Autopilot de extremo a extremo: el servicio sirve solo el v2 (con auth), la BD dockerizada tiene el esquema completo, y el webhook emite cert + gate automáticamente.

**Architecture:** T1 nuevo `asgi.py` (solo v2_router) + Dockerfile; T2 `docker_init` aplica migraciones por glob; T3 el `ci_webhook` cierra el lazo cert+gate (degradable).

**Tech Stack:** Python/FastAPI, Docker, pytest.

## Global Constraints

- **Determinismo intacto:** cert y gate son deterministas → automáticos en el webhook; las acciones de Nivel 2 siguen con approve humano (no se tocan).
- **Degradación:** sin firma → cert degrada; sin GitHub App → gate degrada; el webhook responde 200 con `verdict`/`gate` = None.
- **Seguridad:** `asgi.py` monta solo el v2 (autenticado); los endpoints legacy sin auth quedan fuera del servicio. `api.py` se conserva (deprecated, no borrar).
- `python3 -m pytest`; tests con servicios mockeados (sin GitHub/firma reales). Commits terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: `asgi.py` (entrypoint solo-v2) + Dockerfile

**Files:** Create `asgi.py`, `tests/test_asgi.py`; Modify `Dockerfile`.

**Interfaces:** Produces — `asgi.app` (FastAPI con solo el v2_router).

- [ ] **Step 1: Write the failing test** — `tests/test_asgi.py`:

```python
from fastapi.testclient import TestClient

import asgi


def test_asgi_serves_v2_health():
    client = TestClient(asgi.app)
    r = client.get("/v2/health")
    assert r.status_code == 200


def test_asgi_does_not_expose_legacy_analyze():
    client = TestClient(asgi.app)
    # el endpoint legacy /analyze (RAG v1, sin auth) NO debe existir en el entrypoint nuevo
    assert client.post("/analyze", json={"error_log": "x"}).status_code == 404
    assert client.get("/history").status_code == 404
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_asgi.py -q` (no existe `asgi`).

- [ ] **Step 3: Create `asgi.py`** (raíz del repo, junto a `api.py`):

```python
"""Entrypoint de producción de Mnemo Autopilot.

Monta SOLO el API v2 (Autopilot, autenticado). El RAG v1 legacy (`api.py`,
endpoints /analyze,/sync,/history,/stats,/evaluate sin auth) queda deprecated y
FUERA del arranque. El v2 usa getters perezosos, así que no necesita startup_event.
"""
from fastapi import FastAPI

from src.api_v2 import router as v2_router

app = FastAPI(title="Mnemo Autopilot", version="2.0.0")
app.include_router(v2_router)
```

- [ ] **Step 4: Update `Dockerfile`** — añadir el COPY de `asgi.py` y cambiar el CMD. Cambiar la línea `COPY api.py .` por:

```dockerfile
COPY api.py .
COPY asgi.py .
```

y la última línea `CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]` por:

```dockerfile
CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "8080"]
```

(El `HEALTHCHECK` sobre `/v2/health` no cambia.)

- [ ] **Step 5: Run, expect PASS** — `python3 -m pytest tests/test_asgi.py -q`. If `/v2/health` doesn't exist (404 on the first test), check the real health route in `src/api_v2.py` (`grep -n "health" src/api_v2.py`) and fix the test's path to the actual route; the binding assertion is that v2 is served and `/analyze` is NOT. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 6: Commit**

```bash
git add asgi.py Dockerfile tests/test_asgi.py
git commit -m "feat(deploy): asgi.py monta solo el v2 (jubila el entrypoint legacy sin auth)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `docker_init` aplica todas las migraciones (glob)

**Files:** Modify `scripts/docker_init.py`; Test `tests/test_docker_init_migrations.py`.

- [ ] **Step 1: Write the failing test** — `tests/test_docker_init_migrations.py` (el módulo lee env vars al import, así que las seteamos antes):

```python
import importlib
import os


def test_migrations_glob_includes_all(monkeypatch):
    for k in ("DATABASE_URL", "SUPABASE_URL", "SERVICE_ROLE_KEY", "DEMO_EMAIL", "DEMO_PASSWORD"):
        monkeypatch.setenv(k, "dummy")
    import scripts.docker_init as di
    importlib.reload(di)
    migs = di.MIGRATIONS
    # recoge todas las migraciones del directorio, no solo 001-006
    assert any("016" in m for m in migs), "faltan las migraciones del Autopilot (007-016)"
    assert any("002_assurance" in m for m in migs)
    assert migs == sorted(migs), "las migraciones deben aplicarse en orden"
    assert len(migs) >= 16
```

- [ ] **Step 2: Run, expect FAIL** — la `MIGRATIONS` hardcodeada solo tiene 6 entradas → `any("016" ...)` falla.

- [ ] **Step 3: Implement** — en `scripts/docker_init.py`, añadir `import glob` arriba y sustituir la constante `MIGRATIONS` (la lista 001-006) por:

```python
MIGRATIONS = sorted(glob.glob("db/migrations/*.sql"))
```

(`_apply_migrations` no cambia: sigue iterando `MIGRATIONS`, abriendo y ejecutando cada path en orden.)

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_docker_init_migrations.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add scripts/docker_init.py tests/test_docker_init_migrations.py
git commit -m "fix(deploy): docker_init aplica todas las migraciones por glob (no solo 001-006)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: `ci_webhook` cierra el lazo cert + gate

**Files:** Modify `src/api_v2.py` (`ci_webhook`), `src/multitenant_models.py` (`CiWebhookResponse`); Test: extend `tests/test_api_v2_ci.py`.

**Interfaces:** Consumes — `get_certificate_service().generate(user_id, run_id, created_at) -> dict` (incluye `"verdict"`), `get_gate_service().publish(user_id, run_id) -> {"verdict","conclusion","check_run_url"}`. `datetime`/`timezone`/`CI_SERVICE_USER_ID` ya están importados en `api_v2.py`.

- [ ] **Step 1: Add the response fields** to `src/multitenant_models.py` — en `CiWebhookResponse`, añadir tras `triage`:

```python
    verdict: Optional[str] = None
    gate: Optional[str] = None
```

- [ ] **Step 2: Write the failing test** — extend `tests/test_api_v2_ci.py`. Read that file first for the existing webhook harness (HMAC `X-Hub-Signature-256` signing, the `CiRunArtifact` JSON body, the `CI_SERVICE_USER_ID`/`CI_SERVICE_ORG_ID` env setup, and how the ingestion/triage services are stubbed). Then add a test that, after a valid non-deduplicated artifact, the cert + gate are emitted and surfaced — patching the two getters at the `src.api_v2` module level (they're called as plain functions inside the handler, NOT via `Depends`, so `patch` is required, not `dependency_overrides`):

```python
from unittest.mock import patch, MagicMock

def test_webhook_emits_cert_and_gate_after_triage(<existing webhook fixtures>):
    # ... build a valid signed artifact that ingests + triages (reuse the file's helpers) ...
    cert_svc = MagicMock(); cert_svc.generate.return_value = {"verdict": "apto", "risk_score": 0}
    gate_svc = MagicMock(); gate_svc.publish.return_value = {"verdict": "apto", "conclusion": "success", "check_run_url": "u"}
    with patch("src.api_v2.get_certificate_service", return_value=cert_svc), \
         patch("src.api_v2.get_gate_service", return_value=gate_svc):
        r = client.post("/v2/ci/webhook", data=signed_body, headers=signed_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "apto" and body["gate"] == "success"
    cert_svc.generate.assert_called_once()
    gate_svc.publish.assert_called_once()


def test_webhook_degrades_when_gate_unavailable(<existing webhook fixtures>):
    cert_svc = MagicMock(); cert_svc.generate.return_value = {"verdict": "apto-con-reservas"}
    gate_svc = MagicMock(); gate_svc.publish.side_effect = RuntimeError("no GitHub App")
    with patch("src.api_v2.get_certificate_service", return_value=cert_svc), \
         patch("src.api_v2.get_gate_service", return_value=gate_svc):
        r = client.post("/v2/ci/webhook", data=signed_body, headers=signed_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "apto-con-reservas" and body["gate"] is None   # gate degradó, webhook 200
```

(Adapt the fixture/signing/body to the real `tests/test_api_v2_ci.py` harness — reuse its helpers verbatim. The binding assertions: 200 + `verdict`/`gate` surfaced on success; `gate=None` (and 200) when the gate raises.)

- [ ] **Step 3: Run, expect FAIL** — `verdict`/`gate` not in the response yet (and not emitted).

- [ ] **Step 4: Implement** — en `src/api_v2.py` `ci_webhook`, justo ANTES del `return CiWebhookResponse(...)` final, añadir el lazo (mismo patrón degradable que el triaje), y pasar los nuevos campos al response:

```python
    verdict = None
    gate = None
    if not result.get("deduplicated") and triage_summary is not None:
        try:
            created_at = datetime.now(timezone.utc).isoformat()
            cert = get_certificate_service().generate(
                user_id=CI_SERVICE_USER_ID, run_id=result["run_id"], created_at=created_at)
            verdict = cert.get("verdict")
        except Exception:  # noqa: BLE001 — el cert degrada; la ingesta/triaje ya están commiteados
            logger.exception("certificate failed for run %s", result["run_id"])
        try:
            gate_res = get_gate_service().publish(
                user_id=CI_SERVICE_USER_ID, run_id=result["run_id"])
            gate = gate_res.get("conclusion")
        except Exception:  # noqa: BLE001 — el gate degrada (p.ej. sin GitHub App)
            logger.exception("gate failed for run %s", result["run_id"])
    return CiWebhookResponse(**result, triage=triage_summary, verdict=verdict, gate=gate)
```

(Reemplaza el `return CiWebhookResponse(**result, triage=triage_summary)` actual por el bloque de arriba.)

- [ ] **Step 5: Run, expect PASS** — `python3 -m pytest tests/test_api_v2_ci.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 6: Commit**

```bash
git add src/api_v2.py src/multitenant_models.py tests/test_api_v2_ci.py
git commit -m "feat(ci): el webhook emite cert + publica gate automáticamente tras el triaje (degradable)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **`api.py` se conserva** (deprecated, fuera del arranque) — borrar el RAG v1 + partir los God-objects es limpieza posterior, no H2.
- **El lazo solo corre cuando hubo triaje** (`not deduplicated` + `triage_summary is not None`): un run deduplicado no re-emite cert/gate.
- **`verdict` viene del certificado** (determinista); `gate` es la `conclusion` del check run. Ambos `None` si degradaron — el webhook nunca rompe.
- **Fuera de alcance:** el seed de demo (3 escenarios + 2ª org), UI/ROI/PDF (Bloque C); borrar la legacy + God-objects; Bloque D.
