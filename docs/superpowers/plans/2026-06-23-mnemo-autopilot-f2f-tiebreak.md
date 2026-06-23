# Mnemo Autopilot — F2f: desempate LLM de los ambiguos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolver los veredictos ambiguos (`status='needs_tiebreak'`) con el LLM local de forma **explícita** (`POST /v2/triage/run/{id}/resolve`), fuera del camino crítico, degradando con elegancia si el LLM no decide.

**Architecture:** `src/triage/tiebreaker.py` (`parse_category` puro + `LLMTiebreaker` que usa el provider de forma perezosa, devuelve `None` si falla/no decide). `TriageService.resolve_tiebreaks` (inyecta el tiebreaker) carga los `needs_tiebreak`, los resuelve y persiste vía `repo.update_triage_verdict`. Un endpoint POST lo dispara; el GET sigue siendo lectura pura.

**Tech Stack:** Python 3.13, FastAPI, pytest. Tiebreaker y servicio testeables sin LLM (provider/tiebreaker mockeados).

## Global Constraints

- El desempate se dispara con **`POST /v2/triage/run/{id}/resolve`** (NO perezoso en el GET — el LLM local es lento). El `GET /v2/triage/run/{id}` **no cambia**.
- `LLMTiebreaker.resolve(evidence) -> Optional[Tuple[str,str]]` devuelve `(categoría, razón)` con `categoría ∈ {flaky, infra, maintenance, real}`, o **`None`** si el LLM falla/está ausente o la respuesta no es parseable (degrada → el ambiguo se queda `needs_tiebreak`). Captura excepciones.
- Al resolver un ambiguo: `confidence=0.70`, `llm_assisted=True`, `requires_approval=True` (lo que decide el LLM SIEMPRE pasa por humano), `status='resolved'`, y el `evidence_bundle` se enriquece con `llm_assisted=True` + `tiebreak_reason` + `tiebreak_category`.
- El provider LLM: `LLMProvider.complete(prompt: str) -> str`; obtener vía `get_llm_provider()` (`src/llm/factory.py`); pasar la salida por `strip_reasoning` (`src/llm/reasoning.py`) — igual que `src/assurance/narrator.py`.
- Membership en `update_triage_verdict` (el pooler bypassa RLS). typing.Optional/Tuple/Dict (no PEP 604). Params `%s`. Commit `<type>: <description>`.

---

### Task 1: `src/triage/tiebreaker.py` — `parse_category` (puro) + `LLMTiebreaker`

**Files:**
- Create: `src/triage/tiebreaker.py`
- Test: `tests/test_triage_tiebreaker.py`

**Interfaces:**
- Consumes: `get_llm_provider` (`src/llm/factory.py`), `strip_reasoning` (`src/llm/reasoning.py`), `LLMProvider` (`src/llm/provider.py`).
- Produces: `parse_category(text: str) -> Optional[str]`; `LLMTiebreaker(provider: Optional[LLMProvider]=None)` con `resolve(evidence: Dict[str,Any]) -> Optional[Tuple[str,str]]`.

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_triage_tiebreaker.py
from src.triage.tiebreaker import LLMTiebreaker, parse_category


def test_parse_category_finds_valid():
    assert parse_category("La categoría es real porque hay aserción") == "real"
    assert parse_category("FLAKY: intermitente") == "flaky"
    assert parse_category("Esto es maintenance, la app cambió") == "maintenance"
    assert parse_category("categoría: infra (red caída)") == "infra"


def test_parse_category_earliest_wins():
    # si aparecen varias, gana la primera por posición
    assert parse_category("parece real pero podría ser flaky") == "real"


def test_parse_category_none_when_absent():
    assert parse_category("no estoy seguro") is None
    assert parse_category("") is None
    # palabras que CONTIENEN una categoría pero no son la palabra (word boundary)
    assert parse_category("infrastructure-as-code") is None


class _FakeProvider:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc

    def complete(self, prompt: str) -> str:
        if self._exc:
            raise self._exc
        return self._resp


def test_llm_tiebreaker_valid_returns_category_and_reason():
    tb = LLMTiebreaker(provider=_FakeProvider(resp="Categoría: real. Razón: aserción que falla."))
    result = tb.resolve({"error_type": "AssertionError", "signals": [], "rule_applied": "R6_unknown"})
    assert result is not None
    cat, reason = result
    assert cat == "real" and "aserción" in reason.lower()


def test_llm_tiebreaker_unparseable_returns_none():
    tb = LLMTiebreaker(provider=_FakeProvider(resp="No puedo determinarlo"))
    assert tb.resolve({"error_type": "X", "signals": []}) is None


def test_llm_tiebreaker_exception_returns_none():
    tb = LLMTiebreaker(provider=_FakeProvider(exc=RuntimeError("LLM caído")))
    assert tb.resolve({"error_type": "X", "signals": []}) is None
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_tiebreaker.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.tiebreaker`.

- [ ] **Step 3: Implementar**

```python
# src/triage/tiebreaker.py
import re
from typing import Any, Dict, Optional, Tuple

from src.llm.factory import get_llm_provider
from src.llm.provider import LLMProvider
from src.llm.reasoning import strip_reasoning

_VALID = ("flaky", "infra", "maintenance", "real")


def parse_category(text: str) -> Optional[str]:
    """Extrae la categoría de la respuesta del LLM: la primera de las 4 válidas
    que aparezca como palabra (case-insensitive). None si no hay ninguna."""
    if not text:
        return None
    low = text.lower()
    best_cat: Optional[str] = None
    best_pos = len(low) + 1
    for cat in _VALID:
        m = re.search(rf"\b{cat}\b", low)
        if m and m.start() < best_pos:
            best_pos = m.start()
            best_cat = cat
    return best_cat


def _build_prompt(evidence: Dict[str, Any]) -> str:
    signals = evidence.get("signals", []) or []
    active = [s.get("name") for s in signals if s.get("value")]
    return (
        "Eres un ingeniero de QA clasificando un fallo de test que el motor "
        "determinista no pudo clasificar. Elige EXACTAMENTE una categoría:\n"
        "- flaky: pasa/falla de forma intermitente sin cambios reales.\n"
        "- infra: problema de entorno, red o infraestructura.\n"
        "- maintenance: el test está desactualizado (la app cambió de forma legítima).\n"
        "- real: defecto real del producto.\n\n"
        f"error_type: {evidence.get('error_type')}\n"
        f"señales activas: {', '.join(a for a in active if a) or 'ninguna'}\n"
        f"regla determinista: {evidence.get('rule_applied')}\n\n"
        "Responde empezando por la categoría (una de: flaky, infra, maintenance, real) "
        "y luego una razón breve en una frase."
    )


class LLMTiebreaker:
    """Desempata un ambiguo con el LLM. Degrada a None si el LLM falla o no decide.
    El provider se obtiene de forma perezosa (no en __init__) salvo que se inyecte."""

    def __init__(self, provider: Optional[LLMProvider] = None):
        self._provider = provider

    def resolve(self, evidence: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        try:
            provider = self._provider or get_llm_provider()
            raw = strip_reasoning(provider.complete(_build_prompt(evidence)))
        except Exception:  # noqa: BLE001 — el tiebreak degrada; nunca propaga
            return None
        category = parse_category(raw)
        if category is None:
            return None
        return category, (raw or "").strip()[:1000]
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_tiebreaker.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/triage/tiebreaker.py tests/test_triage_tiebreaker.py
git commit -m "feat(triage): LLMTiebreaker + parse_category (desempate de ambiguos)"
```

---

### Task 2: `AssuranceRepository.update_triage_verdict`

**Files:**
- Modify: `src/defects/repository.py` (método al final de la clase)
- Test: `tests/test_triage_repository.py` (integration; añadir)

**Interfaces:**
- Consumes: `_connect`/`_set_claims`/`Json`; la tabla `triage_verdicts` (F2d).
- Produces: `update_triage_verdict(*, user_id, verdict_id, category, confidence, requires_approval, llm_assisted, status, evidence_bundle) -> bool` (False si no miembro/no existe).

- [ ] **Step 1: Escribir los tests (integration; añadir a `tests/test_triage_repository.py`)**

```python
def test_update_triage_verdict_roundtrip(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="upd",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    fid = out["failures"][0]["failure_id"]
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[{
        "failure_id": fid, "category": "unknown", "confidence": 0.0,
        "rule_applied": "R6_unknown", "evidence_bundle": {"k": "v"},
        "requires_approval": True, "llm_assisted": False, "status": "needs_tiebreak"}])
    vid = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]["id"]
    ok = repo.update_triage_verdict(
        user_id=u, verdict_id=vid, category="real", confidence=0.70,
        requires_approval=True, llm_assisted=True, status="resolved",
        evidence_bundle={"k": "v", "tiebreak_reason": "porque sí"})
    assert ok is True
    got = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]
    assert got["category"] == "real" and got["confidence"] == 0.70
    assert got["llm_assisted"] is True and got["status"] == "resolved"
    assert got["evidence_bundle"]["tiebreak_reason"] == "porque sí"


def test_update_triage_verdict_rejects_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="updnm",
                           items=[_item("t1", "x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[{
        "failure_id": repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["failure_id"],
        "category": "unknown", "confidence": 0.0, "rule_applied": "R6_unknown",
        "evidence_bundle": None, "requires_approval": True, "llm_assisted": False,
        "status": "needs_tiebreak"}])
    vid = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]["id"]
    assert repo.update_triage_verdict(
        user_id=str(uuid.uuid4()), verdict_id=vid, category="real", confidence=0.70,
        requires_approval=True, llm_assisted=True, status="resolved",
        evidence_bundle={}) is False
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_repository.py -v -k update_triage_verdict`
Expected: FAIL — `AttributeError: ... 'update_triage_verdict'`.

- [ ] **Step 3: Implementar** — añadir al final de `AssuranceRepository`

```python
    def update_triage_verdict(
        self, *, user_id: str, verdict_id: str, category: str, confidence: float,
        requires_approval: bool, llm_assisted: bool, status: str,
        evidence_bundle: Any,
    ) -> bool:
        """Actualiza un veredicto (resolución de tiebreak). Membership-gated vía el
        org del veredicto. Devuelve False si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.triage_verdicts tv set category = %s, confidence = %s,"
                    "  requires_approval = %s, llm_assisted = %s, status = %s, evidence_bundle = %s"
                    " where tv.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = tv.org_id and m.user_id = %s)",
                    (category, confidence, requires_approval, llm_assisted, status,
                     Json(evidence_bundle), verdict_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_repository.py -v -k update_triage_verdict`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_triage_repository.py
git commit -m "feat(triage): update_triage_verdict (resolución de tiebreak persistida)"
```

---

### Task 3: `TriageService.resolve_tiebreaks` (tiebreaker inyectado)

**Files:**
- Modify: `src/triage/service.py` (añadir `tiebreaker` a `__init__` + método `resolve_tiebreaks`)
- Test: `tests/test_triage_service.py` (añadir)

**Interfaces:**
- Consumes: `LLMTiebreaker` (Task 1), `repo.get_triage_for_run` (F2d), `repo.update_triage_verdict` (Task 2).
- Produces: `TriageService(*, repo, threshold=..., tiebreaker=None)` (default `LLMTiebreaker()`); `resolve_tiebreaks(*, user_id, run_id) -> Dict[str,int]` (`{"resolved": n, "pending": m}`).

- [ ] **Step 1: Escribir los tests (añadir a `tests/test_triage_service.py`)**

```python
def test_resolve_tiebreaks_resolves_only_pending():
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [
        {"id": "v1", "failure_id": "f1", "category": "real", "confidence": 0.85,
         "rule_applied": "R4_real_recurrent", "evidence_bundle": {}, "requires_approval": False,
         "llm_assisted": False, "status": "resolved"},
        {"id": "v2", "failure_id": "f2", "category": "unknown", "confidence": 0.0,
         "rule_applied": "R6_unknown", "evidence_bundle": {"signals": []}, "requires_approval": True,
         "llm_assisted": False, "status": "needs_tiebreak"},
    ]
    tb = MagicMock()
    tb.resolve.return_value = ("flaky", "intermitente")
    svc = TriageService(repo=repo, tiebreaker=tb)
    out = svc.resolve_tiebreaks(user_id="u", run_id="r1")
    assert out == {"resolved": 1, "pending": 0}
    repo.update_triage_verdict.assert_called_once()
    kw = repo.update_triage_verdict.call_args.kwargs
    assert kw["verdict_id"] == "v2" and kw["category"] == "flaky" and kw["confidence"] == 0.70
    assert kw["llm_assisted"] is True and kw["requires_approval"] is True and kw["status"] == "resolved"
    assert kw["evidence_bundle"]["tiebreak_reason"] == "intermitente"
    assert kw["evidence_bundle"]["tiebreak_category"] == "flaky"


def test_resolve_tiebreaks_leaves_pending_when_undecided():
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [
        {"id": "v2", "failure_id": "f2", "category": "unknown", "confidence": 0.0,
         "rule_applied": "R6_unknown", "evidence_bundle": {}, "requires_approval": True,
         "llm_assisted": False, "status": "needs_tiebreak"},
    ]
    tb = MagicMock()
    tb.resolve.return_value = None
    svc = TriageService(repo=repo, tiebreaker=tb)
    assert svc.resolve_tiebreaks(user_id="u", run_id="r1") == {"resolved": 0, "pending": 1}
    repo.update_triage_verdict.assert_not_called()


def test_resolve_tiebreaks_no_pending():
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_triage_for_run.return_value = [{"id": "v1", "status": "resolved", "evidence_bundle": {}}]
    svc = TriageService(repo=repo, tiebreaker=MagicMock())
    assert svc.resolve_tiebreaks(user_id="u", run_id="r1") == {"resolved": 0, "pending": 0}
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_service.py -v -k resolve_tiebreaks`
Expected: FAIL — `TypeError` (sin `tiebreaker`) / `AttributeError` (sin `resolve_tiebreaks`).

- [ ] **Step 3: Implementar** — en `src/triage/service.py`

Añadir el import:
```python
from src.triage.tiebreaker import LLMTiebreaker
```

Cambiar `__init__` para aceptar el tiebreaker (default `LLMTiebreaker()`, sin default mutable):
```python
    def __init__(self, *, repo, threshold: int = TRIAGE_MASS_COFAILURE_MIN, tiebreaker=None):
        self.repo = repo
        self.threshold = threshold
        self.tiebreaker = tiebreaker or LLMTiebreaker()
```

Añadir el método (tras `triage_run`):
```python
    def resolve_tiebreaks(self, *, user_id: str, run_id: str) -> Dict[str, int]:
        """Resuelve los veredictos 'needs_tiebreak' del run con el tiebreaker (LLM).
        Los que el tiebreaker no decide se quedan pendientes. Devuelve {resolved, pending}."""
        verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
        pending = [v for v in verdicts if v["status"] == "needs_tiebreak"]
        resolved = 0
        for v in pending:
            result = self.tiebreaker.resolve(v["evidence_bundle"] or {})
            if result is None:
                continue
            category, reason = result
            bundle = dict(v["evidence_bundle"] or {})
            bundle.update({
                "llm_assisted": True, "tiebreak_category": category, "tiebreak_reason": reason,
            })
            self.repo.update_triage_verdict(
                user_id=user_id, verdict_id=v["id"], category=category, confidence=0.70,
                requires_approval=True, llm_assisted=True, status="resolved", evidence_bundle=bundle,
            )
            resolved += 1
        return {"resolved": resolved, "pending": len(pending) - resolved}
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_service.py -v`
Expected: todos PASS (los 4 previos de F2e + los 3 nuevos).

- [ ] **Step 5: Commit**

```bash
git add src/triage/service.py tests/test_triage_service.py
git commit -m "feat(triage): resolve_tiebreaks (orquesta el desempate de ambiguos)"
```

---

### Task 4: Endpoint `POST /v2/triage/run/{id}/resolve`

**Files:**
- Modify: `src/api_v2.py` (endpoint nuevo)
- Test: `tests/test_api_v2_triage.py` (añadir)

**Interfaces:**
- Consumes: `get_triage_service` (F2e), `TriageService.resolve_tiebreaks` (Task 3), `get_current_user`.
- Produces: `POST /v2/triage/run/{run_id}/resolve` → `Dict[str,int]` (`{resolved, pending}`).

- [ ] **Step 1: Escribir los tests (añadir a `tests/test_api_v2_triage.py`)**

```python
def test_resolve_endpoint_returns_summary():
    svc = MagicMock()
    svc.resolve_tiebreaks.return_value = {"resolved": 2, "pending": 1}
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_triage_service] = lambda: svc
    app.dependency_overrides[api_v2.get_current_user] = _user
    client = TestClient(app)
    resp = client.post("/v2/triage/run/r1/resolve")
    assert resp.status_code == 200
    assert resp.json() == {"resolved": 2, "pending": 1}
    svc.resolve_tiebreaks.assert_called_once_with(user_id="user-1", run_id="r1")


def test_resolve_endpoint_requires_auth():
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_triage_service] = lambda: MagicMock()
    client = TestClient(app)  # sin override de usuario → 401
    assert client.post("/v2/triage/run/r1/resolve").status_code == 401


def test_resolve_endpoint_db_error_is_502():
    svc = MagicMock()
    svc.resolve_tiebreaks.side_effect = psycopg.OperationalError("db down")
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_triage_service] = lambda: svc
    app.dependency_overrides[api_v2.get_current_user] = _user
    client = TestClient(app)
    assert client.post("/v2/triage/run/r1/resolve").status_code == 502
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_api_v2_triage.py -v -k resolve`
Expected: FAIL — 404 (la ruta no existe).

- [ ] **Step 3: Implementar** — añadir en `src/api_v2.py` (tras `triage_run_v2`, el GET de F2e)

```python
@router.post("/triage/run/{run_id}/resolve")
def resolve_triage_run_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: TriageService = Depends(get_triage_service),
) -> Dict[str, int]:
    try:
        return service.resolve_tiebreaks(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
```

(Confirmar que `Dict` está importado de `typing` en `api_v2.py`; si falta, añadirlo.)

- [ ] **Step 4: Ejecutar (pasa) + suite completa**

Run: `pytest tests/test_api_v2_triage.py -v && pytest -m "not integration" -q`
Expected: tests del endpoint PASS; suite unitaria completa verde (sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add src/api_v2.py tests/test_api_v2_triage.py
git commit -m "feat(triage): POST /v2/triage/run/{id}/resolve (dispara el desempate)"
```

---

## Self-Review

**1. Cobertura del spec (F2f):**
- `tiebreaker.py` (`parse_category` puro + `LLMTiebreaker` con provider perezoso, degrada a None) → Task 1. ✓
- `update_triage_verdict` (membership-gated) → Task 2. ✓
- `resolve_tiebreaks` (carga needs_tiebreak, resuelve, persiste 0.70/llm_assisted/requires_approval/resolved + tiebreak_reason; None → pendiente) → Task 3. ✓
- `POST /v2/triage/run/{id}/resolve` (auth, 502; GET sin cambios) → Task 4. ✓
- Degradación (LLM ausente/falla → None → pendiente, sin romper) → Task 1 (resolve captura) + Task 3 (None → no actualiza). ✓

**2. Placeholders:** ninguno; código completo + comandos con salida esperada.

**3. Consistencia de tipos:** `LLMTiebreaker.resolve -> Optional[Tuple[str,str]]` (Task 1) lo consume `resolve_tiebreaks` (Task 3); `resolve_tiebreaks` llama a `update_triage_verdict` (Task 2) con las claves exactas y lee `id`/`status`/`evidence_bundle` que `get_triage_for_run` (F2d) devuelve; el endpoint (Task 4) inyecta `get_triage_service` (F2e) y devuelve `Dict[str,int]`. `confidence=0.70` encaja con la columna `double precision` (F2d fix). `requires_approval=True` (doble: `0.70<0.80` y `llm_assisted`).

**Nota:** el GET `/v2/triage/run/{id}` (F2e) no se toca — sigue siendo lectura pura. La resolución es explícita vía POST.

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-23-mnemo-autopilot-f2f-tiebreak.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> Continúa en `feat/mnemo-triage` (mismo PR de F2). Con F2f, **F2 (el cerebro de triaje) queda completo**: ingesta → señales → motor determinista → desempate LLM de los ambiguos, todo auditable. Tasks 1, 3 y 4 son testeables sin BD/LLM (mocks); la Task 2 toca la BD (test integration). Siguiente gran bloque: F3 (acción/self-heal).
