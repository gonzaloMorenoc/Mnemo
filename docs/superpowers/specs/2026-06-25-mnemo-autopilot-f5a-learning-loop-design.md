# Mnemo Autopilot — F5a: Lazo de aprendizaje (el foso) (diseño)

**Fecha:** 2026-06-25 · **Fase:** F5a (primera de F5, §7.x del spec maestro) · **Rama:** `feat/mnemo-learning` (desde `main`; autónoma — usa triaje+familias de F2, ya en main; no depende de F4 cert/gate)

## Objetivo

**Calibración privada por cliente** mediante un lazo de aprendizaje determinista: cuando un humano etiqueta una familia de defectos, (1) esa decisión se convierte en el **prior** que el motor de triaje aplica a futuros fallos de esa familia (regla **R0**, todas las categorías), (2) la corrección queda registrada como **historia auditable** ("el motor dijo X, el humano dijo Y"), y (3) una **métrica de precisión por cliente** demuestra el valor. Es el **foso** competitivo: el motor mejora con cada cliente, on-premise, coste API 0 €. Construye sobre la semilla existente (`defect_families.label` → `family_label` → R1), generalizándola, capturándola y midiéndola.

## Decisiones (confirmadas)

- **Enfoque A (prior por etiqueta de familia + R0).** El prior vigente = `defect_families.label`; `triage_corrections` guarda la historia. (No pesos aprendidos ni prior estadístico — refinamientos futuros.)
- **R0 unificado + red de seguridad.** El "prior humano" se mueve de `known_flaky_family` (hoy en R1, solo flaky) a una regla **R0** que cubre todas las categorías, **antes** de R1. `known_flaky_family` se **retira de R1** (que queda solo con `retry`/`intermittent`). R0 **no aplica** si hay señal fuerte de defecto real novedoso (`assertion_failure AND novel`) → cede a R4/R5, para no silenciar un bug real recién introducido por el gate.
- **`triage_corrections` append-only + RLS** (invariante del proyecto). `defect_families.label` sigue siendo el prior vigente (no se duplica).
- **Determinista, on-premise, coste 0.** Sin LLM en el lazo (R0 resuelve en el motor, antes de que el caso llegue al desempate).
- **Endpoints:** `PATCH /v2/defects/{family_id}/label` (cablea `set_family_label`, hoy sin endpoint) y `GET /v2/calibration/metrics`.
- **Base `main`** (no apilado sobre F4); posible conflicto menor en `api_v2.py` al mergear (manejable).

## Componentes

### Motor (`src/triage/signals.py`, `src/triage/engine.py`) — R0 + refactor R1

- **`Signals`**: añadir `family_label: str` (la categoría etiquetada por el humano, `"unknown"` por defecto). Retirar `known_flaky_family` (R0 lo subsume). `compute_signals` copia `family_label` de `FailureInput.family_label` (que ya existe).
- **R0 (nueva, antes de R1)** en `engine.py`:
  ```python
  _HUMAN_CATEGORIES = ("flaky", "real", "maintenance", "infra")

  # R0 — prior humano calibrado (todas las categorías), salvo señal fuerte de real novedoso
  if signals.family_label in _HUMAN_CATEGORIES and not (signals.assertion_failure and signals.novel):
      return TriageVerdict(category=signals.family_label, confidence=0.95,
                           rule_applied="R0_calibrated", requires_approval=False,
                           llm_assisted=False, ambiguous=False)
  ```
  R0 construye el `TriageVerdict` directamente (no vía `_verdict`): `requires_approval=False` porque el humano ya clasificó la familia (sign-off explícito). Confianza 0.95 (> `_APPROVAL_THRESHOLD` 0.80).
- **R1 (modificada):** `if signals.retry_passed_in_run or signals.intermittent_same_sha:` (se quita `or signals.known_flaky_family`). R2–R6 intactas.
- El motor sigue **puro** (función de `Signals`). Los tests F2 de R1 que usaban `known_flaky_family`/`family_label="flaky"` pasan a probar R0; R1 se prueba con `retry`/`intermittent`.

### Datos — migración `015_triage_corrections.sql`

```sql
create table if not exists public.triage_corrections (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    family_id uuid not null references public.defect_families (id) on delete cascade,
    engine_category text,                 -- lo que el motor decidió (snapshot), nullable si no había veredicto
    human_category text not null,         -- lo que el humano eligió
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
grant select, insert on public.triage_corrections to authenticated;  -- append-only (sin update/delete)
```

### Repo (`src/defects/repository.py`)

- **`set_family_label` (refactor):** además del `UPDATE defect_families SET label`, lee el `engine_category` de la familia (categoría del veredicto más reciente de un fallo de esa familia: `triage_verdicts tv JOIN failures f ON f.id=tv.failure_id WHERE f.defect_family_id=%s ORDER BY tv.created_at DESC LIMIT 1`; `None` si no hay) e **inserta una fila en `triage_corrections`** (`engine_category`, `human_category=label`, `corrected_by=user_id`, `source='family_label'`, `reason`). Membership-gated; valida que la familia es del org. Devuelve el `org_id` (para el endpoint). Acepta `reason: Optional[str]`.
- **`get_calibration_metrics(*, user_id, org_id) -> Dict`:** agrega `triage_corrections` del org → `{total, aciertos (engine_category==human_category), accuracy (aciertos/total, 0.0 si total=0), familias_calibradas (count distinct defect_families con label != 'unknown'), por_categoria}`. Membership-gated.

### Endpoints (`src/api_v2.py`, `Depends(get_current_user)`)

| Método | Ruta | Notas |
|---|---|---|
| PATCH | `/v2/defects/{family_id}/label` | Body `{label, reason?}`; valida `label ∈ {flaky,real,maintenance,infra,unknown}`; cablea `set_family_label` → `{family_id, label}` |
| GET | `/v2/calibration/metrics?org_id={org_id}` | métrica del foso por org (membership-gated; `org_id` como query param) |

Errores: 401 sin auth · `label` inválida → 422 · familia inexistente/sin acceso → 404 · `psycopg.Error` → 502.

## Testing (TDD)

- **Motor (puro, `tests/test_triage_engine.py`):** R0 calibrado por categoría (flaky/real/maintenance/infra); red de seguridad (`family_label="flaky"` + `assertion_failure` + `novel` → R4/R5, **no** R0); `family_label="unknown"` → R0 no aplica (R1–R6 como hoy); R1 con `retry`/`intermittent` (ya sin `known_flaky_family`). Actualizar los tests F2 afectados por el refactor R1.
- **Repo (integración Postgres):** `set_family_label` inserta en `triage_corrections` con el `engine_category` correcto (incluido el caso sin veredicto → `None`); `get_calibration_metrics` agrega bien (acuerdo vs corrección, accuracy, familias calibradas); aislamiento por-org; migración 015 (RLS + grants append-only).
- **Endpoints:** PATCH setea label + corrección (200), `label` inválida (422), familia inexistente (404), sin auth (401); GET métricas (200 con los campos).

## Fases (tareas del plan)

1. **Motor:** R0 + refactor R1/`Signals` (`family_label`, retirar `known_flaky_family`) + tests del motor.
2. **Datos + repo:** migración `015` + `set_family_label` (registra corrección) + `get_calibration_metrics` + tests de integración.
3. **Endpoints:** `PATCH /v2/defects/{id}/label` + `GET /v2/calibration/metrics` + wiring `api_v2` + tests.

## Fuera de alcance (YAGNI / fases posteriores)

- **Short-circuit del desempate LLM** con el prior (resolver veredictos `needs_tiebreak` viejos sin llamar al LLM) → follow-up; R0 ya calibra los veredictos nuevos en el motor.
- Feedback **implícito** de `approve`/`reject` de acciones como señal de calibración (hoy: etiquetado explícito).
- Prior **estadístico** (enfoque C) / pesos aprendidos (enfoque B).
- `rejected_by` en `actions`; historia de labels en `defect_families`.
- **F5b** (frontend: bandeja, veredictos, certificado, gate) · **F6** (demo).
