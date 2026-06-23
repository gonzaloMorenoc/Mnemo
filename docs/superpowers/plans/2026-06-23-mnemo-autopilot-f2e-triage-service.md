# Mnemo Autopilot — F2e: servicio de triaje + wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El `TriageService` que orquesta la cadena de triaje (`get_triage_inputs → mass_cofailure → compute_signals → triage → build_evidence → save_triage_verdicts`), corriendo **inline tras la ingesta del webhook** y expuesto vía `GET /v2/triage/run/{id}` — convirtiendo el triaje en algo que clasifica runs reales de extremo a extremo.

**Architecture:** `src/triage/service.py` (`TriageService.triage_run`) une el repositorio (F2d) con el motor puro (F2b/c): carga los hechos por fallo, calcula `mass_cofailure` a nivel de run (vía `classify_error`), clasifica cada fallo y persiste los veredictos (los ambiguos como `needs_tiebreak` para F2f). El webhook lo invoca tras la ingesta, **degradando con elegancia** (un fallo de triaje no rompe la ingesta ya commiteada). Un endpoint nuevo expone los veredictos persistidos.

**Tech Stack:** Python 3.13, FastAPI, pytest. El servicio es testeable con el repo mockeado (sin BD/LLM).

## Global Constraints

- `TriageService.triage_run` orquesta: `get_triage_inputs` → `mass_cofailure` (run-level: nº de fallos con `classify_error`→`infra` ≥ `TRIAGE_MASS_COFAILURE_MIN`, default 3) → por fallo `compute_signals` → `triage` → `build_evidence` → `save_triage_verdicts`. `status='needs_tiebreak'` si `verdict.ambiguous`, si no `'resolved'`.
- `mass_cofailure` es **run-level** (mismo valor para todos los fallos del run).
- El **LLM tiebreak NO está en F2e** (es F2f); los ambiguos quedan `needs_tiebreak`, `llm_assisted=False`.
- El triaje corre **inline tras la ingesta** del webhook, pero **degrada con elegancia**: un fallo de triaje se loguea y devuelve `triage=null` (la ingesta ya está commiteada; el triaje se puede recomputar). NO se corre si el run fue **deduplicado**.
- Endpoint `GET /v2/triage/run/{id}` con `Depends(get_current_user)` + membership (vía repo). Mapeo de errores `/v2`: 401, 502.
- typing.Optional/List/Dict (no PEP 604) en módulos compartidos. Tests del servicio con repo mockeado; webhook/endpoint con mocks. Commit `<type>: <description>`.

---

### Task 1: Config `TRIAGE_MASS_COFAILURE_MIN`

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py` (añadir)

**Interfaces:**
- Produces: `src.config.TRIAGE_MASS_COFAILURE_MIN: int` (default 3).

- [ ] **Step 1: Escribir el test**

```python
# tests/test_config.py — añadir
def test_triage_mass_cofailure_min_present():
    import src.config as config
    assert hasattr(config, "TRIAGE_MASS_COFAILURE_MIN")
    assert isinstance(config.TRIAGE_MASS_COFAILURE_MIN, int)
    assert config.TRIAGE_MASS_COFAILURE_MIN >= 1
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_config.py::test_triage_mass_cofailure_min_present -v`
Expected: FAIL — `AttributeError` / `hasattr` False.

- [ ] **Step 3: Implementar** — añadir a `src/config.py` (tras las constantes de CI)

```python
# Triaje (Mnemo Autopilot F2): nº mínimo de fallos con firma de infra en un run
# para considerarlo "co-fallo masivo" (señal de problema de entorno, no de producto).
TRIAGE_MASS_COFAILURE_MIN = int(os.getenv("TRIAGE_MASS_COFAILURE_MIN", "3"))
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(triage): config TRIAGE_MASS_COFAILURE_MIN"
```

---

### Task 2: `TriageService.triage_run` (orquestación)

**Files:**
- Create: `src/triage/service.py`
- Test: `tests/test_triage_service.py`

**Interfaces:**
- Consumes: `AssuranceRepository.get_triage_inputs` / `save_triage_verdicts` (F2d), `classify_error` (`src/triage/patterns.py`), `FailureInput`/`compute_signals` (`src/triage/signals.py`), `triage` (`src/triage/engine.py`), `build_evidence` (`src/triage/evidence.py`), `TRIAGE_MASS_COFAILURE_MIN` (Task 1).
- Produces: `TriageService(*, repo, threshold=TRIAGE_MASS_COFAILURE_MIN)` con `triage_run(*, user_id, run_id) -> Dict[str, int]` (conteos por categoría; `{}` si no es miembro/no existe el run; persiste los veredictos).

- [ ] **Step 1: Escribir los tests (unit, repo mockeado)**

```python
# tests/test_triage_service.py
from unittest.mock import MagicMock

from src.triage.service import TriageService


def _failure(test_name, error_type, message, **over):
    base = {
        "failure_id": f"fid-{test_name}", "fingerprint": f"fp-{test_name}",
        "family_id": f"fam-{test_name}", "lineage_projects": ["p"],
        "error_type": error_type, "message": message, "trace": None,
        "is_novel": True, "family_label": "unknown", "retry_passed_in_run": False,
        "intermittent_same_sha": False, "has_green_baseline": False, "dom_changed": False,
    }
    base.update(over)
    return base


def _svc(failures, threshold=3):
    repo = MagicMock()
    repo.get_triage_inputs.return_value = {
        "run": {"id": "r1", "org_id": "o1", "project": "p", "commit_sha": "sha"},
        "failures": failures,
    }
    repo.save_triage_verdicts.return_value = len(failures)
    return TriageService(repo=repo, threshold=threshold), repo


def test_non_member_returns_empty_and_does_not_save():
    repo = MagicMock()
    repo.get_triage_inputs.return_value = {"run": None, "failures": []}
    svc = TriageService(repo=repo, threshold=3)
    assert svc.triage_run(user_id="u", run_id="r1") == {}
    repo.save_triage_verdicts.assert_not_called()


def test_flaky_classified_and_persisted():
    svc, repo = _svc([_failure("t1", "Error", "boom", known_flaky_family=False,
                               retry_passed_in_run=True)])
    counts = svc.triage_run(user_id="u", run_id="r1")
    assert counts["flaky"] == 1
    _, kw = repo.save_triage_verdicts.call_args
    v = kw["verdicts"][0]
    assert v["failure_id"] == "fid-t1" and v["category"] == "flaky"
    assert v["status"] == "resolved" and v["evidence_bundle"]["rule_applied"] == "R1_flaky"


def test_mass_cofailure_makes_infra():
    # 3 fallos con firma de infra → mass_cofailure True → categoría infra (R2)
    fs = [_failure(f"t{i}", "Error", "connect ECONNREFUSED 127.0.0.1") for i in range(3)]
    svc, repo = _svc(fs, threshold=3)
    counts = svc.triage_run(user_id="u", run_id="r1")
    assert counts["infra"] == 3
    # con umbral 4, los mismos 3 NO son co-fallo masivo → no infra
    svc2, _ = _svc([_failure(f"t{i}", "Error", "connect ECONNREFUSED x") for i in range(3)], threshold=4)
    assert svc2.triage_run(user_id="u", run_id="r1").get("infra", 0) == 0


def test_ambiguous_marked_needs_tiebreak():
    # locator error sin baseline/dom_changed → ambiguo
    svc, repo = _svc([_failure("t1", "TimeoutError", "waiting for locator")])
    svc.triage_run(user_id="u", run_id="r1")
    v = repo.save_triage_verdicts.call_args.kwargs["verdicts"][0]
    assert v["category"] == "unknown" and v["status"] == "needs_tiebreak"
    assert v["requires_approval"] is True and v["llm_assisted"] is False
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_service.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.service`.

- [ ] **Step 3: Implementar**

```python
# src/triage/service.py
from typing import Any, Dict

from src.config import TRIAGE_MASS_COFAILURE_MIN
from src.triage.engine import triage
from src.triage.evidence import build_evidence
from src.triage.patterns import classify_error
from src.triage.signals import FailureInput, compute_signals

_CATEGORIES = ("flaky", "infra", "maintenance", "real", "unknown")


class TriageService:
    """Orquesta el triaje de un run: carga los hechos (repo), calcula mass_cofailure
    a nivel de run, clasifica cada fallo con el motor determinista y persiste los
    veredictos. Los ambiguos quedan 'needs_tiebreak' (el desempate LLM es F2f)."""

    def __init__(self, *, repo, threshold: int = TRIAGE_MASS_COFAILURE_MIN):
        self.repo = repo
        self.threshold = threshold

    def triage_run(self, *, user_id: str, run_id: str) -> Dict[str, int]:
        data = self.repo.get_triage_inputs(user_id=user_id, run_id=run_id)
        if data["run"] is None:
            return {}
        failures = data["failures"]

        infra_count = sum(
            1 for f in failures
            if "infra" in classify_error(f["error_type"], f["message"], f["trace"])
        )
        mass = infra_count >= self.threshold

        counts = {c: 0 for c in _CATEGORIES}
        verdicts = []
        for f in failures:
            signals = compute_signals(FailureInput(
                error_type=f["error_type"], message=f["message"], trace=f["trace"],
                is_novel=f["is_novel"], family_label=f["family_label"],
                retry_passed_in_run=f["retry_passed_in_run"],
                intermittent_same_sha=f["intermittent_same_sha"],
                mass_cofailure=mass,
                has_green_baseline=f["has_green_baseline"], dom_changed=f["dom_changed"],
            ))
            verdict = triage(signals)
            evidence = build_evidence(
                fingerprint=f["fingerprint"], family_id=f["family_id"],
                lineage_projects=f["lineage_projects"], error_type=f["error_type"],
                signals=signals, verdict=verdict,
            )
            verdicts.append({
                "failure_id": f["failure_id"],
                "category": verdict.category,
                "confidence": verdict.confidence,
                "rule_applied": verdict.rule_applied,
                "evidence_bundle": evidence,
                "requires_approval": verdict.requires_approval,
                "llm_assisted": verdict.llm_assisted,
                "status": "needs_tiebreak" if verdict.ambiguous else "resolved",
            })
            counts[verdict.category] = counts.get(verdict.category, 0) + 1

        self.repo.save_triage_verdicts(
            user_id=user_id, org_id=data["run"]["org_id"], run_id=run_id, verdicts=verdicts,
        )
        return counts
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_service.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/triage/service.py tests/test_triage_service.py
git commit -m "feat(triage): TriageService.triage_run (orquestación determinista)"
```

---

### Task 3: Wiring en el webhook + endpoint `GET /v2/triage/run/{id}`

**Files:**
- Modify: `src/multitenant_models.py` (añadir `triage` a `CiWebhookResponse` + `TriageVerdictResponse`)
- Modify: `src/api_v2.py` (singleton `get_triage_service`, wiring en `ci_webhook`, endpoint nuevo)
- Test: `tests/test_api_v2_ci.py` (actualizar) y `tests/test_api_v2_triage.py` (nuevo)

**Interfaces:**
- Consumes: `TriageService` (Task 2), `AssuranceRepository.get_triage_for_run` (F2d).
- Produces: `CiWebhookResponse.triage: Optional[Dict[str,int]]`; `TriageVerdictResponse`; `GET /v2/triage/run/{id}`; el webhook corre triaje inline (degradando) salvo en dedup.

- [ ] **Step 1: Escribir los tests** (actualizar `tests/test_api_v2_ci.py` make_client + 2 tests; crear `tests/test_api_v2_triage.py`)

En `tests/test_api_v2_ci.py`, actualizar `make_client` para mockear también `get_triage_service`, y añadir dos tests:
```python
def make_client(service, monkeypatch, triage=None):
    monkeypatch.setattr(api_v2, "CI_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(api_v2, "CI_SERVICE_USER_ID", "svc-user")
    monkeypatch.setattr(api_v2, "get_ci_ingestion_service", lambda: service)
    if triage is None:
        triage = MagicMock()
        triage.triage_run.return_value = {"flaky": 0, "infra": 0, "maintenance": 0, "real": 0, "unknown": 0}
    monkeypatch.setattr(api_v2, "get_triage_service", lambda: triage)
    app = FastAPI()
    app.include_router(api_v2.router)
    return TestClient(app)


def test_webhook_runs_triage_and_includes_summary(monkeypatch):
    service = _ok_service()  # returns deduplicated=False, run_id="r1"
    triage = MagicMock()
    triage.triage_run.return_value = {"flaky": 1, "infra": 0, "maintenance": 0, "real": 2, "unknown": 0}
    client = make_client(service, monkeypatch, triage=triage)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    triage.triage_run.assert_called_once_with(user_id="svc-user", run_id="r1")
    assert resp.json()["triage"] == {"flaky": 1, "infra": 0, "maintenance": 0, "real": 2, "unknown": 0}


def test_webhook_skips_triage_on_dedup(monkeypatch):
    service = MagicMock()
    service.ingest_artifact.return_value = {
        "run_id": "r1", "ingested": 0, "known": 0, "novel": 0,
        "results_recorded": 0, "snapshots_saved": 0, "deduplicated": True,
    }
    triage = MagicMock()
    client = make_client(service, monkeypatch, triage=triage)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    triage.triage_run.assert_not_called()
    assert resp.json()["triage"] is None


def test_webhook_triage_failure_degrades(monkeypatch):
    service = _ok_service()
    triage = MagicMock()
    triage.triage_run.side_effect = RuntimeError("boom")
    client = make_client(service, monkeypatch, triage=triage)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200  # la ingesta no se rompe
    assert resp.json()["triage"] is None
```

`tests/test_api_v2_triage.py` (nuevo):
```python
import psycopg
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(repo, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_triage_run_returns_verdicts():
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [
        {"id": "v1", "failure_id": "f1", "category": "real", "confidence": 0.85,
         "rule_applied": "R4_real_recurrent", "evidence_bundle": {"k": "v"},
         "requires_approval": False, "llm_assisted": False, "status": "resolved"},
    ]
    client = make_client(repo)
    resp = client.get("/v2/triage/run/r1")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["category"] == "real" and body[0]["status"] == "resolved"
    assert body[0]["evidence_bundle"] == {"k": "v"}


def test_triage_run_requires_auth():
    client = make_client(MagicMock(), with_user=False)
    assert client.get("/v2/triage/run/r1").status_code == 401


def test_triage_run_db_error_is_502():
    repo = MagicMock()
    repo.get_triage_for_run.side_effect = psycopg.OperationalError("db down")
    client = make_client(repo)
    assert client.get("/v2/triage/run/r1").status_code == 502
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_api_v2_triage.py tests/test_api_v2_ci.py -v`
Expected: FAIL — `get_triage_service` / `TriageVerdictResponse` / la ruta no existen.

- [ ] **Step 3: Añadir los modelos** en `src/multitenant_models.py`

Añadir `triage` a `CiWebhookResponse` (campo opcional, default None) — leer la clase y añadir:
```python
    triage: Optional[Dict[str, int]] = None
```
(Confirmar que `Dict` y `Optional` están importados de `typing` en el módulo; si falta `Dict`, añadirlo al import.)

Añadir la clase nueva:
```python
class TriageVerdictResponse(BaseModel):
    id: str
    failure_id: str
    category: str
    confidence: float
    rule_applied: str
    requires_approval: bool
    llm_assisted: bool
    status: str
    evidence_bundle: Optional[dict] = None
```

- [ ] **Step 4: Wiring en `src/api_v2.py`**

Añadir imports:
```python
from src.triage.service import TriageService
```
Añadir `TriageVerdictResponse` a la importación desde `src.multitenant_models`.

Tras el singleton `_ci_ingestion_service` (y su getter), añadir:
```python
_triage_service = None


def get_triage_service() -> TriageService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _triage_service
    if _triage_service is None:
        _triage_service = TriageService(repo=get_assurance_repo())
    return _triage_service
```

En `ci_webhook`, tras obtener `result` del `service.ingest_artifact(...)` (y su bloque de manejo de errores) y ANTES del `return`, sustituir el `return` por:
```python
    triage_summary = None
    if not result.get("deduplicated"):
        try:
            triage_summary = get_triage_service().triage_run(
                user_id=CI_SERVICE_USER_ID, run_id=result["run_id"]
            )
        except Exception:  # noqa: BLE001 — el triaje degrada; la ingesta ya está commiteada
            logger.exception("triage failed for run %s", result["run_id"])
    return CiWebhookResponse(**result, triage=triage_summary)
```

Añadir el endpoint (tras `ci_webhook`):
```python
@router.get("/triage/run/{run_id}", response_model=List[TriageVerdictResponse])
def triage_run_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> List[TriageVerdictResponse]:
    try:
        verdicts = repo.get_triage_for_run(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [TriageVerdictResponse(**v) for v in verdicts]
```

- [ ] **Step 5: Ejecutar (pasa) + suite completa**

Run: `pytest tests/test_api_v2_triage.py tests/test_api_v2_ci.py -v && pytest -m "not integration" -q`
Expected: tests de triaje/webhook PASS; suite unitaria completa verde (sin regresiones).

- [ ] **Step 6: Commit**

```bash
git add src/api_v2.py src/multitenant_models.py tests/test_api_v2_ci.py tests/test_api_v2_triage.py
git commit -m "feat(triage): wiring inline en el webhook + GET /v2/triage/run/{id}"
```

---

## Self-Review

**1. Cobertura del spec (F2e):**
- `TriageService` orquesta get_triage_inputs→mass_cofailure→compute_signals→triage→build_evidence→save (§3.5, §5) → Task 2. ✓
- mass_cofailure run-level vía classify_error ≥ umbral (§3.1) → Task 1 + Task 2. ✓
- Triaje inline tras la ingesta, degradando, skip en dedup (§3.5) → Task 3. ✓
- Ambiguos → `needs_tiebreak` (para F2f) → Task 2. ✓
- `GET /v2/triage/run/{id}` (§7) + resumen de triaje en la respuesta del webhook → Task 3. ✓

**2. Placeholders:** ninguno; código completo + comandos con salida esperada.

**3. Consistencia de tipos:** `TriageService(repo=...).triage_run(user_id, run_id) -> Dict[str,int]` (Task 2) lo invoca el webhook (Task 3); construye `FailureInput` con las claves que `get_triage_inputs` (F2d) devuelve y los verdict-dicts con las claves que `save_triage_verdicts` (F2d) espera; `TriageVerdictResponse` (Task 3) mapea las claves de `get_triage_for_run` (F2d). `triage` en `CiWebhookResponse` es `Optional[Dict[str,int]]`.

**Nota:** el triaje degrada con un `except Exception` deliberado (la ingesta ya está commiteada; un fallo de triaje no debe romper el webhook ni perder la ingesta). Es el mismo patrón que el narrator del veredicto. El triaje se puede recomputar (idempotente) vía re-ingesta o un re-trigger.

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-23-mnemo-autopilot-f2e-triage-service.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> Continúa en `feat/mnemo-triage` (mismo PR de F2). Tras F2e, el triaje corre de extremo a extremo en backend (postear un run → cada fallo clasificado y consultable). Queda **F2f** (desempate LLM perezoso de los `needs_tiebreak`). Tasks 1-3 son testeables sin BD (servicio con repo mockeado; webhook/endpoint mockeados).
