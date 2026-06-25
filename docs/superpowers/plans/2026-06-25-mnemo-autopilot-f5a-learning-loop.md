# F5a — Lazo de aprendizaje (el foso) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calibración privada por cliente: el humano etiqueta una familia → regla R0 calibrada en el motor (todas las categorías, con red de seguridad) + historia auditable (`triage_corrections`) + métrica de precisión por cliente.

**Architecture:** El motor de triaje es puro (`triage(signals) -> TriageVerdict`); una nueva regla R0 antes de R1 aplica el prior humano (`family_label`, que ya llega en `Signals`). `set_family_label` (hoy sin endpoint) pasa a registrar la corrección. Una métrica agrega la historia. Determinista, sin LLM en el lazo.

**Tech Stack:** Python 3.13, FastAPI, psycopg, pytest (+ `@pytest.mark.integration` para Postgres).

## Global Constraints

- **R0 antes de R1; red de seguridad:** R0 aplica el prior `family_label ∈ {flaky,real,maintenance,infra}` con `confidence=0.95`, `rule_applied="R0_calibrated"`, `requires_approval=False`, `llm_assisted=False`, `ambiguous=False` — **salvo** `assertion_failure AND novel` (posible defecto real nuevo → cede a R4/R5).
- **R1 pierde `known_flaky_family`:** queda `retry_passed_in_run OR intermittent_same_sha`. `Signals` pasa a tener `family_label: str` y pierde `known_flaky_family`.
- **Determinista, sin LLM en el lazo.** El motor sigue siendo función pura de `Signals`.
- **`triage_corrections` append-only + RLS** `is_org_member` + `force` + `grant select, insert` (invariante del proyecto).
- **Multitenant:** cada método de repo valida membership; el pooler bypasea RLS.
- **Errores `/v2`:** 401 sin auth · `label` inválida (`ValueError`) → 422 · familia/org inexistente o sin acceso → 404 · `psycopg.Error` → 502.
- `DATABASE_URL` (.env) **es producción**: aplicar la migración 015 con `psql` (Bash con `dangerouslyDisableSandbox`); los tests de integración corren contra esa BD (cleanup en fixtures).
- Commits `feat:`/`refactor:`/`test:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`. Tests con `python3 -m pytest`.

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `src/triage/signals.py` | modificar | `family_label` en `Signals`; retirar `known_flaky_family` |
| `src/triage/engine.py` | modificar | regla R0; R1 sin `known_flaky_family` |
| `tests/test_triage_engine.py` | modificar | R0 + red de seguridad; R1 actualizado |
| `db/migrations/015_triage_corrections.sql` | crear | tabla append-only + RLS |
| `src/defects/repository.py` | modificar | `set_family_label` registra corrección; `get_calibration_metrics` |
| `tests/test_triage_repository.py` | modificar | integración: corrección + métricas |
| `src/multitenant_models.py` | modificar | modelos de request/response |
| `src/api_v2.py` | modificar | endpoints PATCH label + GET metrics |
| `tests/test_api_v2_calibration.py` | crear | endpoints |

---

## Task 1: Motor — regla R0 + refactor R1/`Signals`

**Files:**
- Modify: `src/triage/signals.py`, `src/triage/engine.py`
- Test: `tests/test_triage_engine.py`

**Interfaces:**
- Produces: `Signals` con campo `family_label: str` (sin `known_flaky_family`); `triage(signals)` aplica R0 (`rule_applied="R0_calibrated"`) antes de R1.

- [ ] **Step 1: Update the engine tests** in `tests/test_triage_engine.py`.

Replace the `_sig` base helper (swap `known_flaky_family=False` for `family_label="unknown"`):

```python
def _sig(**over):
    base = dict(
        infra_error=False, locator_error=False, assertion_failure=False,
        retry_passed_in_run=False, intermittent_same_sha=False, family_label="unknown",
        mass_cofailure=False, has_green_baseline=False, dom_changed=False,
        novel=False, recurrent=False,
    )
    base.update(over)
    return Signals(**base)
```

Replace `test_r1_flaky_by_intermittency_or_known_family` (R1 no longer keys on the family label):

```python
def test_r1_flaky_by_intermittency():
    assert triage(_sig(intermittent_same_sha=True)).category == "flaky"
    assert triage(_sig(intermittent_same_sha=True)).rule_applied == "R1_flaky"
```

Replace `test_priority_flaky_over_infra` (a human-labeled family is now R0, which wins over everything):

```python
def test_priority_r0_over_other_rules():
    v = triage(_sig(family_label="flaky", mass_cofailure=True, infra_error=True))
    assert v.category == "flaky" and v.rule_applied == "R0_calibrated"  # R0 antes que R2
```

Add the R0 tests:

```python
def test_r0_calibrated_each_category():
    for cat in ("flaky", "real", "maintenance", "infra"):
        v = triage(_sig(family_label=cat))
        assert v.category == cat and v.rule_applied == "R0_calibrated"
        assert v.confidence == 0.95 and v.requires_approval is False
        assert v.llm_assisted is False and v.ambiguous is False


def test_r0_safety_net_yields_to_real_novel():
    # familia etiquetada flaky pero aserción + novedoso → posible bug real nuevo → R5, no R0
    v = triage(_sig(family_label="flaky", assertion_failure=True, novel=True))
    assert v.category == "real" and v.rule_applied == "R5_real_novel"


def test_r0_does_not_fire_on_unknown_label():
    # family_label='unknown' → R0 no aplica; cae en R1-R6 como antes
    assert triage(_sig(family_label="unknown", retry_passed_in_run=True)).rule_applied == "R1_flaky"
    assert triage(_sig(family_label="unknown", assertion_failure=True, novel=True)).rule_applied == "R5_real_novel"


def test_r0_recurrent_real_in_flaky_family_stays_calibrated():
    # aserción recurrente (no novel) en familia flaky → la red solo protege lo NOVEDOSO → R0 flaky
    v = triage(_sig(family_label="flaky", assertion_failure=True, recurrent=True))
    assert v.category == "flaky" and v.rule_applied == "R0_calibrated"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_triage_engine.py -q` → FAIL (`Signals` has no `family_label`; no `R0_calibrated`).

- [ ] **Step 3: Update `Signals`** in `src/triage/signals.py`.

In the `Signals` dataclass (lines ~24-36) remove `known_flaky_family: bool` and add `family_label: str`:

```python
@dataclass
class Signals:
    infra_error: bool
    locator_error: bool
    assertion_failure: bool
    retry_passed_in_run: bool
    intermittent_same_sha: bool
    family_label: str
    mass_cofailure: bool
    has_green_baseline: bool
    dom_changed: bool
    novel: bool
    recurrent: bool
```

In `compute_signals` replace the `known_flaky_family=...` line with `family_label=failure.family_label`:

```python
        intermittent_same_sha=failure.intermittent_same_sha,
        family_label=failure.family_label,
        mass_cofailure=failure.mass_cofailure,
```

- [ ] **Step 4: Add R0 and trim R1** in `src/triage/engine.py`.

Add the constant after `_APPROVAL_THRESHOLD`:

```python
_HUMAN_CATEGORIES = ("flaky", "real", "maintenance", "infra")
```

Insert R0 as the first check inside `triage` (before the R1 `if`), and remove `known_flaky_family` from R1:

```python
def triage(signals: Signals) -> TriageVerdict:
    """Clasificación determinista por reglas de prioridad. R0 aplica el prior humano
    calibrado; el ambiguo (R6) queda 'unknown' + ambiguous=True para el desempate LLM."""
    # R0 — prior humano calibrado (todas las categorías), salvo señal fuerte de real novedoso
    if signals.family_label in _HUMAN_CATEGORIES and not (signals.assertion_failure and signals.novel):
        return TriageVerdict(
            category=signals.family_label, confidence=0.95, rule_applied="R0_calibrated",
            requires_approval=False, llm_assisted=False, ambiguous=False,
        )
    if signals.retry_passed_in_run or signals.intermittent_same_sha:
        return _verdict("flaky", 0.90, "R1_flaky")
    if signals.mass_cofailure and signals.infra_error:
        return _verdict("infra", 0.90, "R2_infra")
    if (signals.locator_error and not signals.assertion_failure
            and signals.has_green_baseline and signals.dom_changed):
        return _verdict("maintenance", 0.80, "R3_maintenance")
    if signals.assertion_failure and signals.recurrent:
        return _verdict("real", 0.85, "R4_real_recurrent")
    if signals.assertion_failure and signals.novel:
        return _verdict("real", 0.75, "R5_real_novel", novel=True)
    return TriageVerdict(
        category="unknown", confidence=0.0, rule_applied="R6_ambiguous",
        requires_approval=True, llm_assisted=False, ambiguous=True,
    )
```

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_triage_engine.py -q` → PASS. Then `python3 -m pytest tests/ -m "not integration" -q -k "triage or signal"` to catch any other consumer of `Signals`/`compute_signals` (e.g. `tests/test_triage_signals.py`); if a test constructs `Signals(known_flaky_family=...)` or `FailureInput`, it must be updated to `family_label=...`. Fix any such fallout (they're in the triage test modules).

- [ ] **Step 6: Commit**

```bash
git add src/triage/signals.py src/triage/engine.py tests/test_triage_engine.py
git commit -m "refactor(triage): regla R0 calibrada (prior humano) + R1 sin known_flaky_family

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: Datos + repo — migración 015, corrección y métricas

**Files:**
- Create: `db/migrations/015_triage_corrections.sql`
- Modify: `src/defects/repository.py`
- Test: `tests/test_triage_repository.py`

**Interfaces:**
- Consumes: `family_label` from R0 (Task 1) is fed by `defect_families.label`, written here.
- Produces: `set_family_label(*, user_id, family_id, label, reason=None) -> bool` (now also records a correction); `get_calibration_metrics(*, user_id, org_id) -> Optional[Dict]` → `{total, aciertos, accuracy, familias_calibradas, por_categoria}` (None if not a member).

- [ ] **Step 1: Migration**

Create `db/migrations/015_triage_corrections.sql`:

```sql
-- db/migrations/015_triage_corrections.sql
-- Mnemo Autopilot F5a: historia auditable del lazo de aprendizaje (motor vs humano).

create table if not exists public.triage_corrections (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    family_id uuid not null references public.defect_families (id) on delete cascade,
    engine_category text,
    human_category text not null,
    source text not null default 'family_label',
    reason text,
    corrected_by uuid references auth.users (id),
    corrected_at timestamptz not null default now()
);
create index if not exists idx_triage_corrections_org on public.triage_corrections (org_id, corrected_at desc);

alter table public.triage_corrections enable row level security;
alter table public.triage_corrections force row level security;
drop policy if exists triage_corrections_member on public.triage_corrections;
create policy triage_corrections_member on public.triage_corrections for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert on public.triage_corrections to authenticated;  -- append-only
```

Apply it (production DB): `set -a && source .env && set +a && psql "$DATABASE_URL" -f db/migrations/015_triage_corrections.sql` (Bash con `dangerouslyDisableSandbox`).

- [ ] **Step 2: Write the failing integration tests** in `tests/test_triage_repository.py` (append; reuse the file's existing `org`/`repo` fixtures pattern — inspect the top of the file to match fixture names).

```python
import uuid as _uuid

import pytest


@pytest.mark.integration
def test_set_family_label_records_correction(assurance_repo, seeded_family):
    # seeded_family: dict with user_id, org_id, family_id, and a recent verdict category 'real'
    repo, ctx = assurance_repo, seeded_family
    ok = repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"],
                               label="flaky", reason="histórico flaky")
    assert ok is True
    metrics = repo.get_calibration_metrics(user_id=ctx["user_id"], org_id=ctx["org_id"])
    assert metrics["total"] == 1
    # engine dijo 'real', humano dijo 'flaky' → no es acierto
    assert metrics["aciertos"] == 0
    assert metrics["familias_calibradas"] == 1
    assert metrics["por_categoria"].get("flaky") == 1


@pytest.mark.integration
def test_set_family_label_non_member_returns_false(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    assert repo.set_family_label(user_id=str(_uuid.uuid4()), family_id=ctx["family_id"],
                                 label="flaky") is False


@pytest.mark.integration
def test_get_calibration_metrics_non_member_is_none(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    assert repo.get_calibration_metrics(user_id=str(_uuid.uuid4()), org_id=ctx["org_id"]) is None


@pytest.mark.integration
def test_set_family_label_invalid_label_raises(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    with pytest.raises(ValueError):
        repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"], label="bogus")
```

**The `seeded_family` fixture:** this file already tests `set_family_label` (F2d work), so it already has a fixture that seeds an org + a `defect_families` row — **reuse/extend that one** rather than inventing it. Extend it to also insert a `failures` row linked to that family (`defect_family_id`) and a `triage_verdicts` row for that failure with `category='real'`, so `engine_category` is populated when the correction is recorded. The fixture must `yield {user_id, org_id, family_id}` and clean up the org + auth user on teardown. Read the existing fixture in this file (and `tests/test_certify_repository.py` for the org/auth.users seed + cleanup pattern) to get the exact per-schema `INSERT` columns — do not guess column names. If the existing fixture already yields these values under different keys, adapt the test bodies to those keys instead of renaming the fixture.

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_triage_repository.py -q -k "correction or calibration or label"` → FAIL (`get_calibration_metrics` missing; `set_family_label` doesn't accept `reason`).

- [ ] **Step 4: Refactor `set_family_label` and add `get_calibration_metrics`** in `src/defects/repository.py`.

Replace `set_family_label` (currently lines ~822-838):

```python
    def set_family_label(self, *, user_id: str, family_id: str, label: str,
                         reason: Optional[str] = None) -> bool:
        """Etiqueta una familia (lazo de aprendizaje) y registra la corrección
        (motor vs humano) en triage_corrections. Devuelve False si no es miembro /
        no existe. Lanza ValueError si el label no es válido."""
        if label not in ("flaky", "real", "maintenance", "infra", "unknown"):
            raise ValueError(f"invalid label: {label!r}")
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.defect_families set label = %s"
                    " where id = %s and (scope = 'global' or exists (select 1 from public.memberships m"
                    "   where m.org_id = public.defect_families.org_id and m.user_id = %s))"
                    " returning org_id",
                    (label, family_id, user_id),
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    return False
                org_id = row["org_id"]
                if org_id is not None:
                    cur.execute(
                        "select tv.category from public.triage_verdicts tv"
                        " join public.failures f on f.id = tv.failure_id"
                        " where f.defect_family_id = %s order by tv.created_at desc limit 1",
                        (family_id,),
                    )
                    er = cur.fetchone()
                    engine_category = er["category"] if er else None
                    cur.execute(
                        "insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, source, reason, corrected_by)"
                        " values (%s, %s, %s, %s, 'family_label', %s, %s)",
                        (org_id, family_id, engine_category, label, reason, user_id),
                    )
            conn.commit()
        return True

    def get_calibration_metrics(self, *, user_id: str, org_id: str) -> Optional[Dict[str, Any]]:
        """Métrica del foso por org. None si el usuario no es miembro."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return None
                cur.execute(
                    "select count(*) as total,"
                    " count(*) filter (where engine_category = human_category) as aciertos"
                    " from public.triage_corrections where org_id = %s", (org_id,))
                agg = cur.fetchone()
                total, aciertos = agg["total"], agg["aciertos"]
                cur.execute("select count(*) as n from public.defect_families"
                            " where org_id = %s and label is not null and label <> 'unknown'", (org_id,))
                familias_calibradas = cur.fetchone()["n"]
                cur.execute("select human_category, count(*) as n from public.triage_corrections"
                            " where org_id = %s group by human_category", (org_id,))
                por_categoria = {r["human_category"]: r["n"] for r in cur.fetchall()}
        return {"total": total, "aciertos": aciertos,
                "accuracy": (aciertos / total) if total else 0.0,
                "familias_calibradas": familias_calibradas, "por_categoria": por_categoria}
```

(Ensure `Optional`, `Dict`, `Any` are imported at the top of the module — they already are, since other methods use them.)

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_triage_repository.py -q` → PASS (new + existing; needs DB + migration 015 applied).

- [ ] **Step 6: Commit**

```bash
git add db/migrations/015_triage_corrections.sql src/defects/repository.py tests/test_triage_repository.py
git commit -m "feat(learning): migración 015 + set_family_label registra corrección + get_calibration_metrics

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Endpoints — PATCH label + GET metrics

**Files:**
- Modify: `src/multitenant_models.py`, `src/api_v2.py`
- Test: `tests/test_api_v2_calibration.py`

**Interfaces:**
- Consumes: `set_family_label` / `get_calibration_metrics` (Task 2) via `get_assurance_repo()`.
- Produces: `PATCH /v2/defects/{family_id}/label`, `GET /v2/calibration/metrics`.

- [ ] **Step 1: Models** in `src/multitenant_models.py`:

```python
class SetFamilyLabelRequest(BaseModel):
    label: str
    reason: Optional[str] = None


class FamilyLabelResponse(BaseModel):
    family_id: str
    label: str


class CalibrationMetricsResponse(BaseModel):
    total: int
    aciertos: int
    accuracy: float
    familias_calibradas: int
    por_categoria: dict
```

- [ ] **Step 2: Write the failing endpoint tests** in `tests/test_api_v2_calibration.py`:

```python
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, repo=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_set_label_ok():
    repo = MagicMock()
    repo.set_family_label.return_value = True
    resp = _client(repo=repo).patch("/v2/defects/fam-1/label", json={"label": "flaky"})
    assert resp.status_code == 200 and resp.json()["label"] == "flaky"
    assert repo.set_family_label.call_args.kwargs["family_id"] == "fam-1"


def test_set_label_invalid_is_422():
    repo = MagicMock()
    repo.set_family_label.side_effect = ValueError("invalid label: 'bogus'")
    resp = _client(repo=repo).patch("/v2/defects/fam-1/label", json={"label": "bogus"})
    assert resp.status_code == 422


def test_set_label_not_found_is_404():
    repo = MagicMock()
    repo.set_family_label.return_value = False
    resp = _client(repo=repo).patch("/v2/defects/fam-1/label", json={"label": "flaky"})
    assert resp.status_code == 404


def test_metrics_ok():
    repo = MagicMock()
    repo.get_calibration_metrics.return_value = {
        "total": 3, "aciertos": 2, "accuracy": 0.6667,
        "familias_calibradas": 2, "por_categoria": {"flaky": 2, "real": 1}}
    resp = _client(repo=repo).get("/v2/calibration/metrics?org_id=org-1")
    assert resp.status_code == 200 and resp.json()["total"] == 3


def test_metrics_non_member_is_404():
    repo = MagicMock()
    repo.get_calibration_metrics.return_value = None
    assert _client(repo=repo).get("/v2/calibration/metrics?org_id=org-1").status_code == 404


def test_endpoints_require_auth():
    assert _client(repo=MagicMock(), with_user=False).get(
        "/v2/calibration/metrics?org_id=o").status_code == 401
```

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_api_v2_calibration.py -q` → FAIL (no endpoints).

- [ ] **Step 4: Wire `api_v2.py`**.

Add the models to the `from src.multitenant_models import (...)` block: `SetFamilyLabelRequest`, `FamilyLabelResponse`, `CalibrationMetricsResponse`.

Add the endpoints (near the other `/defects` endpoints):

```python
@router.patch("/defects/{family_id}/label", response_model=FamilyLabelResponse)
def set_family_label_v2(
    family_id: str,
    body: SetFamilyLabelRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> FamilyLabelResponse:
    try:
        ok = repo.set_family_label(user_id=user.user_id, family_id=family_id,
                                   label=body.label, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if not ok:
        raise HTTPException(status_code=404, detail="defect family not found")
    return FamilyLabelResponse(family_id=family_id, label=body.label)


@router.get("/calibration/metrics", response_model=CalibrationMetricsResponse)
def calibration_metrics_v2(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> CalibrationMetricsResponse:
    try:
        metrics = repo.get_calibration_metrics(user_id=user.user_id, org_id=org_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if metrics is None:
        raise HTTPException(status_code=404, detail="org not found or not a member")
    return CalibrationMetricsResponse(**metrics)
```

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_api_v2_calibration.py -q` → PASS (6 passed).

- [ ] **Step 6: Full suite + commit**

Run: `python3 -m pytest -m "not integration" -q` → green. Then:

```bash
git add src/multitenant_models.py src/api_v2.py tests/test_api_v2_calibration.py
git commit -m "feat(learning): endpoints PATCH /defects/{id}/label + GET /calibration/metrics

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Despliegue:** aplicar `db/migrations/015_triage_corrections.sql`.
- **El lazo cerrado:** humano hace `PATCH /v2/defects/{id}/label` → `defect_families.label` (prior) + fila en `triage_corrections` (historia) → el siguiente run de esa familia entra por **R0** (calibrado, sin LLM, sin approval) → `GET /v2/calibration/metrics` muestra la precisión por cliente.
- **Familias `global`** (`org_id` NULL): se permite etiquetar pero **no** se registra corrección (el lazo es por-org); es intencional.
- **Fuera de alcance:** short-circuit del desempate LLM con el prior; feedback implícito de approve/reject; frontend (F5b).
