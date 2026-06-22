# Spec — Mnemo Autopilot F2: el cerebro de triaje (determinista) + ingesta atómica/idempotente

**Fecha:** 2026-06-22
**Rama:** `feat/mnemo-triage` (apilada sobre `feat/mnemo-autopilot` / F1, PR #11)
**Contexto:** F2 del plan de Mnemo Autopilot (`docs/superpowers/specs/2026-06-22-mnemo-autopilot-design.md`, §5 y §19). Consume los datos que F1 ingiere (`test_results`, `dom_snapshots`, `defect_families`) y emite, por cada fallo, un veredicto de triaje **determinista y auditable**.

---

## 1. Objetivo y no-objetivos

**Objetivo:** un **motor de triaje determinista** que clasifica cada fallo de un run en una de cuatro categorías — **defecto real / flaky / mantenimiento / infra** — con confianza calibrada y un `evidence_bundle` auditable, persistido en `triage_verdicts`. Más, como cimiento, **ingesta atómica + idempotente** para que el motor razone sobre datos limpios.

**No-objetivos (roadmap):**
- Acceso al repo de código / señal "el test no cambió" → **F3** (refina mantenimiento, sube su confianza).
- Self-heal, tickets, cuarentena, gate, certificado → F3/F4.
- Bandeja de aprobación / frontend → F5 (F2 solo expone los datos vía API).
- Clasificador entrenado (Opción 3) → el lazo de F5 acumula su dataset.

## 2. Decisiones de diseño fijadas

1. **Mantenimiento sin repo:** F2 clasifica las 4 categorías con las señales disponibles. Mantenimiento = `locator_error` + `has_green_baseline` + `dom_changed`, a confianza media-alta (0.80). El refinamiento "el test no cambió" lo aporta **F3** subiendo la confianza. Sin baseline o sin `dom_changed` → ambiguo.
2. **Idempotencia por `run_uid`, NO por commit:** la señal de flaky por intermitencia necesita **varios runs sobre el mismo commit**; deduplicar por `commit_sha` los colapsaría. La clave es un **identificador de run del CI** (`run_uid`, UUID que el reporter genera por run). Dedup por `(org_id, run_uid)`: reintento de la misma entrega → no-op; re-ejecución genuina → run nuevo.
3. **Desempate LLM perezoso:** el triaje determinista corre inline; los ambiguos quedan `needs_tiebreak` y el LLM los resuelve **on-demand, fuera del camino crítico** (degrada a `unknown`/revisión si el LLM no está).

## 3. El motor de triaje

### 3.1. Señales (funciones puras, desde datos de F1)

Por cada fallo, dado su contexto de run y el histórico:

| Señal | Definición |
|---|---|
| `retry_passed_in_run` | el test pasó al reintentar dentro del **mismo** run (de `test_results`: status `flaky` o retried con pass) |
| `intermittent_same_sha` | mismo `test_name` + mismo `commit_sha`, con **mezcla pass+fail** entre runs |
| `known_flaky_family` | la `defect_family` del fallo tiene `label='flaky'` |
| `mass_cofailure` | nº de fallos del run con firma de infra ≥ umbral (`TRIAGE_MASS_COFAILURE_MIN`, default 3) |
| `infra_error` | `error_type`/mensaje casa patrones de infra (`ECONNREFUSED`, `net::ERR`, timeout de red, `Target closed`, `crash`) |
| `locator_error` | casa patrones de locator (`locator … not found`, `strict mode violation`, `not visible`, `waiting for selector/locator`) |
| `assertion_failure` | casa patrones de aserción (`expect(`, `AssertionError`) |
| `dom_changed` | `normalize(dom_fallo) != normalize(dom_último_verde)` |
| `has_green_baseline` | existe un snapshot `last_green` para el test |
| `novel` / `recurrent` | la familia es nueva / conocida (`occurrence_count`) |

`normalize` (DOM): colapsa espacios en blanco; coarse pero suficiente para la señal a confianza calibrada. El diff a nivel de elemento es F3.

### 3.2. Lógica de decisión (pura, determinista, por prioridad)

La primera regla que dispara, gana:

```
R1  retry_passed_in_run OR intermittent_same_sha OR known_flaky_family   → FLAKY         (0.90)
R2  mass_cofailure AND infra_error                                       → INFRA         (0.90)
R3  locator_error AND has_green_baseline AND dom_changed                 → MANTENIMIENTO (0.80)
R4  assertion_failure AND recurrent                                      → DEFECTO REAL  (0.85)
R5  assertion_failure AND novel                                          → DEFECTO REAL  (0.75)
R6  resto (locator sin baseline/sin dom_changed, señales en conflicto)   → AMBIGUO → desempate LLM
```

### 3.3. Confianza, `requires_approval`, desempate

- Reglas deterministas → confianza 0.75–0.90 (tabla arriba).
- **Desempate LLM** (solo R6): recibe el `evidence_bundle`, devuelve categoría + razón; confianza **capada a 0.70**, `llm_assisted=true`. Si el LLM falla/ausente → `category='unknown'`, confianza 0.0, `requires_approval=true`.
- `requires_approval = confianza < 0.80 OR (category='real' AND novel) OR llm_assisted`. Alimenta el gate (F4) y la bandeja (F5).

### 3.4. `evidence_bundle` (persistido, auditable)

```json
{
  "fingerprint": "...", "family_id": "...", "lineage_projects": ["proj-x","proj-y"],
  "error_type": "locator_not_found",
  "signals": [{"name":"dom_changed","value":true},{"name":"has_green_baseline","value":true}],
  "rule_applied": "R3_maintenance",
  "category": "maintenance", "confidence": 0.80,
  "requires_approval": false, "llm_assisted": false
}
```

### 3.5. Dónde corre

- **Determinista inline:** tras la ingesta atómica (mismo flujo del webhook), `TriageService.triage_run(run_id)` carga los fallos del run + histórico + snapshots, computa señales por fallo, aplica el motor y **persiste `triage_verdicts`**. Es por-run (necesita todos los fallos para `mass_cofailure` y el histórico para intermitencia). Barato (SQL + reglas).
- **Desempate LLM perezoso:** los ambiguos se persisten `status='needs_tiebreak'`. `GET /v2/triage/run/{id}` resuelve los pendientes on-demand vía `resolve_tiebreaks` (cachea el resultado en la fila). Degrada con elegancia.

## 4. Ingesta atómica + idempotente (cimiento)

- **Atomicidad:** un método nuevo `AssuranceRepository.ingest_ci_run` funde en **una transacción** lo que hoy hace `ingest_run` + `record_test_results` + `save_dom_snapshots`. `CiIngestionService` pasa a llamarlo. (El `ingest_run` legacy se conserva para los caminos Allure/JUnit/Jira que no traen `test_results`/snapshots.)
- **Idempotencia:** `CiRunArtifact` gana `run_uid: Optional[str]`. `ingest_ci_run`, si `run_uid` viene y ya existe un run con `(org_id, run_uid)`, hace **no-op** y devuelve el run existente (con `deduplicated=true`). Si falta `run_uid`, solo atomicidad (retrocompatible).
- **Reporter (F1b):** añadido mínimo — genera un `run_uid` (UUID) por run y lo incluye en el artefacto. (Cambio pequeño y retrocompatible; se hace en su paquete.)

## 5. Componentes nuevos (interfaces, archivos <400 líneas)

| Módulo | Responsabilidad | Interfaz |
|---|---|---|
| `src/triage/patterns.py` | patrones infra/locator/assertion | `classify_error(error_type, message) -> set[str]` |
| `src/triage/signals.py` | señales puras | `compute_signals(failure, run_ctx, history) -> Signals` (dataclass) |
| `src/triage/engine.py` | reglas deterministas | `triage(signals) -> TriageVerdict` (category, confidence, rule_applied, requires_approval, ambiguous) |
| `src/triage/evidence.py` | bundle auditable | `build_evidence(failure, signals, verdict) -> dict` |
| `src/triage/tiebreaker.py` | desempate LLM | `Tiebreaker` (Protocol) + `LLMTiebreaker` (Ollama perezoso) |
| `src/triage/service.py` | orquestación | `TriageService.triage_run(user_id, run_id)`, `resolve_tiebreaks(user_id, run_id)` |
| `src/defects/repository.py` (extender) | atómico+idempotente + queries de señal + persistencia de veredictos + label | ver §6 |
| `src/ci/models.py` (extender) | `run_uid` + `TriageVerdictResponse` | — |
| `src/api_v2.py` (extender) | wiring inline + `GET /v2/triage/run/{id}` | — |

`Signals` (dataclass): booleanos/enteros de §3.1. `TriageVerdict`: `category`, `confidence`, `rule_applied`, `requires_approval`, `llm_assisted`, `ambiguous`.

## 6. Repositorio (métodos nuevos/modificados)

- `ingest_ci_run(*, user_id, org_id, project, source, run_uid, items, results, snapshots) -> dict` — membership; dedup por `(org_id, run_uid)`; inserta run+failures+familias+test_results+dom_snapshots en **una** transacción; devuelve `{run_id, ingested, known, novel, results_recorded, snapshots_saved, deduplicated}`.
- `get_run_failures_for_triage(*, user_id, run_id) -> list[dict]` — fallos del run con fingerprint, error_type, message, family_id, family label/occurrence.
- `count_mass_cofailure(*, run_id, signature) -> int` y/o devolver los conteos en el bundle de carga.
- `get_intermittency(*, org_id, test_name, commit_sha) -> {pass, fail}` — conteos de outcomes mismo-SHA.
- `get_last_green_dom(*, org_id, project, test_name) -> str | None` y el DOM del fallo.
- `save_triage_verdicts(*, user_id, run_id, verdicts)` y `get_triage_for_run(*, user_id, run_id)`.
- `set_family_label(*, user_id, family_id, label)`.

Todas con chequeo de membership (aislamiento en capa de aplicación; el pooler bypassa RLS).

## 7. Endpoints nuevos (`/v2`, `Depends(get_current_user)`)

| Método | Ruta | Salida |
|---|---|---|
| GET | `/v2/triage/run/{id}` | lista de `TriageVerdictResponse` (resuelve desempates pendientes de forma perezosa) |

El webhook (`POST /v2/ci/webhook`) corre el triaje determinista inline tras la ingesta y devuelve, además de los conteos de F1, un resumen de triaje (conteos por categoría). Errores: patrón `/v2` (401/403/404/422/502/503).

## 8. Modelo de datos (dos migraciones)

**`db/migrations/008_run_uid.sql` (F2a — idempotencia):**
- `test_runs`: `+ run_uid text`; `create unique index idx_test_runs_run_uid on public.test_runs (org_id, run_uid) where run_uid is not null` (único parcial: dedup por `(org_id, run_uid)` sin afectar a runs sin `run_uid`).

**`db/migrations/009_triage.sql` (F2d — triaje):**
- `defect_families`: `+ label text not null default 'unknown' check (label in ('flaky','real','maintenance','infra','unknown'))`.
- `triage_verdicts` (nueva): `id uuid pk`, `failure_id uuid references failures on delete cascade`, `run_id uuid references test_runs on delete cascade`, `org_id uuid references organizations on delete cascade`, `category text check (...)`, `confidence real`, `rule_applied text`, `evidence_bundle jsonb`, `requires_approval bool`, `llm_assisted bool`, `status text check (status in ('resolved','needs_tiebreak')) default 'resolved'`, `created_at timestamptz`. Índices: `(run_id)`, `(org_id)`. RLS `enable`+`force` + policy `is_org_member` + grants a `authenticated` (espejo de 002).

**Idempotencia del re-triaje:** `save_triage_verdicts` **reemplaza** los veredictos existentes del run (delete+insert por `run_id`), de modo que re-triar un run (p. ej. tras un reintento) es idempotente y no duplica filas.

## 9. Testing (TDD, sin BD/Ollama vía mocks salvo `integration`)

- `patterns`: cada patrón infra/locator/assertion clasifica correctamente; no falsos cruces.
- `signals`: cada señal a partir de datos plain (run_ctx/history mockeados).
- `engine`: **table-driven** — una fila por regla (R1–R6) + casos de conflicto → categoría/confianza/`requires_approval`/`ambiguous` correctos. Sin BD/LLM.
- `evidence`: el bundle contiene las señales disparadas, la regla y los campos esperados.
- `tiebreaker`: con LLM mockeado, categoría+razón; degradación (LLM lanza → `unknown`, confianza 0, requires_approval).
- `service`: orquestación con repo+tiebreaker mockeados (triage_run persiste, resolve_tiebreaks resuelve solo los `needs_tiebreak`).
- Repositorio (`integration`): ingesta atómica (un fallo a mitad revierte todo), idempotencia (mismo `run_uid` → no-op + `deduplicated`; distinto → run nuevo), intermitencia mismo-SHA, co-fallo masivo, `save/get_triage_verdicts`, `set_family_label`, aislamiento org A↛org B.
- Endpoint: servicio mockeado (lista veredictos; resuelve pendientes; 404/401/403/502).

## 10. Criterios de aceptación

- [ ] `ingest_ci_run` es atómico (rollback total ante fallo a mitad) e idempotente por `run_uid` (no-op en reintento; run nuevo en re-ejecución). Tests integration verdes.
- [ ] El triaje clasifica correctamente las 6 reglas en la suite table-driven (determinista, sin LLM).
- [ ] `intermittent_same_sha` se detecta con ≥2 runs de outcomes mixtos en el mismo commit.
- [ ] `dom_changed` distingue fallo-vs-último-verde; mantenimiento solo con baseline + cambio.
- [ ] Ambiguos quedan `needs_tiebreak`; `GET /v2/triage/run/{id}` los resuelve perezosamente; el LLM ausente degrada a `unknown` sin romper.
- [ ] `evidence_bundle` persistido y auditable por fallo.
- [ ] Suite unitaria verde sin BD/Ollama; integration verde contra Postgres.
- [ ] Aislamiento multitenant probado en las queries/persistencia nuevas.

## 11. Orden de implementación sugerido (fases del plan)

| Fase | Entrega | Módulos |
|---|---|---|
| **F2a** | Ingesta atómica + idempotente | migración `008_run_uid`, `ingest_ci_run`, `CiRunArtifact.run_uid`, `CiIngestionService` usa el método atómico |
| **F2b** | Patrones + señales (puro) | `patterns.py`, `signals.py` + tests |
| **F2c** | Motor + evidencia (puro) | `engine.py`, `evidence.py` + tests table-driven |
| **F2d** | Repo: queries de señal + persistencia | migración `009_triage` (triage_verdicts, label), queries + `save/get_triage_verdicts`, `set_family_label` (integration) |
| **F2e** | Servicio + wiring | `TriageService.triage_run`, inline en el webhook, resumen de triaje en la respuesta |
| **F2f** | Tiebreaker LLM + endpoint | `tiebreaker.py`, `resolve_tiebreaks`, `GET /v2/triage/run/{id}` |

F2a–F2e dan el triaje determinista e2e; F2f añade el desempate LLM perezoso.

## 12. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Dedup por commit rompería intermitencia | Clave por `run_uid` (identificador de run del CI), no por commit |
| Mantenimiento sin "test no cambió" → falsos positivos | Confianza calibrada (0.80) + `requires_approval`; F3 sube confianza con el repo |
| Triaje en el camino crítico del webhook | Determinista es barato (SQL+reglas); el LLM es perezoso/on-demand |
| Patrones de error frágiles | Conjuntos de patrones testeados y aislados (`patterns.py`); el LLM cubre los que se escapan |
| Ingesta atómica rompe el camino F1 | `ingest_ci_run` es nuevo y específico del CI; `ingest_run` legacy intacto para Allure/JUnit/Jira |
