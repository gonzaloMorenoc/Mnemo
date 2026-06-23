# Mnemo Autopilot — F3a: marco de acción + bandeja de aprobación (diseño)

**Fecha:** 2026-06-23 · **Fase:** F3a (primera de F3, la capa de acción §6 del spec maestro) · **Rama:** `feat/mnemo-actions` (nueva, sobre `main`)

## Objetivo

Convertir los **veredictos de triaje** (F2) en **acciones propuestas** (Nivel 2: nunca se finalizan sin aprobación humana), visibles en una **bandeja de aprobación**. F3a entrega el esqueleto del marco + los **dos actuadores que no escriben en GitHub** (cuarentena y ticket enriquecido), con `CodeHost` como Protocol + stub. El self-heal (F3b) y la GitHub App real (F3c) son fases posteriores.

## Relación con el spec maestro

Implementa §6 (capa de acción) **parcialmente**: §6.2 (cuarentena con deuda) y §6.3 (ticket enriquecido), el marco `Actuator`/`CodeHost` (§6.5 como Protocol, sin la App real), la tabla `actions` (§9) y los endpoints de bandeja/aprobación (§10). Decisión confirmada: la propuesta de acciones se dispara con un **POST explícito** (como el `/resolve` de F2f), porque el actuador de ticket usa el LLM (lento) y no debe ir en el camino crítico del webhook.

## Componentes (`src/actions/`, archivos pequeños)

### `base.py`
- **`ActionProposal`** (dataclass): `kind: str` (`quarantine|ticket|self_heal`), `payload: Dict[str, Any]` (contenido propuesto del artefacto), `summary: str` (línea corta para la bandeja).
- **`Actuator`** (Protocol): `propose(verdict: Dict[str, Any]) -> Optional[ActionProposal]`. El `verdict` es una fila de `get_triage_for_run` (incluye `evidence_bundle` con `family_id`, `lineage_projects`, `error_type`, `signals`…). Devuelve `None` si no aplica.
- **`CodeHost`** (Protocol): `create_issue(*, title, body, labels) -> str` y `open_draft_pr(*, title, body, patch) -> str` (devuelven una URL/ref). **`NullCodeHost`**: stub que registra la intención y devuelve un ref placeholder (`stub://issue/...`). GitHub real = F3c.

### `quarantine.py` — `QuarantineActuator` (determinista, sin LLM)
Veredicto **flaky** → `ActionProposal(kind="quarantine")` con `payload`:
- `debt_ticket`: `{title, body}` — el ticket de deuda (familia flaky, historial, "no se oculta: queda deuda abierta").
- `annotation`: la anotación sugerida del test (`@flaky` / `test.fixme`) + retry sugerido.
**Invariante (test):** una propuesta de cuarentena **siempre** incluye `debt_ticket` no vacío (cuarentena sin ticket = ocultar bugs).

### `ticket.py` — `TicketActuator`
Veredicto **real** → `ActionProposal(kind="ticket")` con `payload = {title, body, labels}`. El `body` enriquecido con: **hipótesis de root-cause** (reutiliza `RootCauseAnalyzer`, anclado en defectos pasados recuperados — **no** se reimplementa), **linaje cross-proyecto** (de `evidence_bundle.lineage_projects` + `get_lineage`), severidad/riesgo del veredicto. `RootCauseAnalyzer` se **inyecta** y **degrada** (si el LLM no está: ticket con linaje + "root-cause no disponible", nunca rompe).

### `service.py` — `ActionService`
- `__init__(*, repo, actuators: Dict[str, Actuator], codehost: CodeHost = NullCodeHost())`. `actuators` mapea **categoría → actuador**: `{"flaky": QuarantineActuator(), "real": TicketActuator(...)}`.
- `propose_actions(*, user_id, run_id) -> Dict[str, int]`: carga `get_triage_for_run`, por cada veredicto `status == "resolved"` busca el actuador de su categoría; si hay, llama `propose(verdict)` y persiste la acción `proposed` (vía repo). Devuelve conteos `{quarantine, ticket, skipped}`. **Idempotente** por run: re-proponer reemplaza solo las acciones `proposed` del run y **preserva** las ya `approved`/`rejected`/`materialized` (no se destruyen decisiones humanas).
- `approve_action(*, user_id, action_id) -> Dict`: materializa el artefacto vía `self.codehost` (stub en F3a), marca `approved` + sign-off (`approved_by`/`approved_at`) + guarda `artifact_ref`. `reject_action(*, user_id, action_id, reason) -> bool`.

**Mapeo categoría → actuador (F3a):** `flaky → quarantine` · `real → ticket` · `maintenance → self_heal` (F3b: se cuenta como `skipped`) · `infra`/`unknown`/`needs_tiebreak` → sin acción (`skipped`).

## Datos — migración `010_actions.sql`

Tabla `public.actions`:
- `id uuid pk`, `triage_verdict_id uuid fk→triage_verdicts on delete cascade`, `run_id uuid fk→test_runs on delete cascade`, `org_id uuid fk→organizations on delete cascade`.
- `kind text check (kind in ('quarantine','ticket','self_heal'))`, `payload jsonb`, `summary text`.
- `status text check (status in ('proposed','approved','rejected','materialized')) default 'proposed'`.
- `artifact_ref text` (null hasta materializar), `approved_by uuid`, `approved_at timestamptz`, `reject_reason text`, `created_at timestamptz default now()`.
- Índices: `(run_id)`, `(org_id, status)`. **RLS** enable+force + policy `is_org_member(org_id)` + grants a `authenticated` (espejo de 002/009).

## Repositorio (`src/defects/repository.py`, extender — membership-gated)
- `save_actions(*, user_id, org_id, run_id, actions: List[Dict]) -> int` — borra solo las acciones `proposed` del run y reinserta (idempotente, **preserva** approved/rejected/materialized); valida membership + `run_id → org_id` (como `record_test_results`).
- `get_actions(*, user_id, org_id, status=None) -> List[Dict]` — la bandeja, filtrada por org (+ status opcional), membership-gated.
- `approve_action(*, user_id, action_id, artifact_ref) -> bool` / `reject_action(*, user_id, action_id, reason) -> bool` — transición de estado por id, membership-gated vía el org de la acción; `False` si no miembro/no existe.

## Endpoints `/v2` (con `Depends(get_current_user)` salvo donde se note)
- `POST /v2/actions/run/{run_id}/propose` → `{quarantine, ticket, skipped}` (dispara la propuesta del run).
- `GET /v2/actions?org_id=&status=proposed` → la **bandeja** de aprobación.
- `POST /v2/actions/{action_id}/approve` → `approved` + sign-off + materializa (stub).
- `POST /v2/actions/{action_id}/reject` (`{reason?}`).
Mapeo de errores `/v2`: 401, 403, 404, 502, 503.

## Flujo

```
POST /v2/actions/run/{id}/propose
  → ActionService.propose_actions
      → get_triage_for_run(run)                       [F2d, reusa]
      → por veredicto resuelto: actuators[categoría].propose(verdict)
            flaky → QuarantineActuator (ticket de deuda + anotación)
            real  → TicketActuator (root-cause + linaje; LLM degradante)
      → save_actions(proposed)
      → {quarantine, ticket, skipped}

POST /v2/actions/{id}/approve
  → ActionService.approve_action → CodeHost.materialize (stub) → repo.approve_action(ref, sign-off)
```

## Manejo de errores / degradación
- **LLM ausente** (root-cause del ticket): el actuador degrada → ticket con linaje + nota "root-cause no disponible". Nunca rompe `propose_actions`.
- **Error de BD**: 502.
- **Aislamiento multitenant**: cada método del repo valida membership (el pooler bypassa RLS). `save_actions` valida además `run_id → org_id`.
- **Nivel 2 estricto**: ninguna acción se materializa sin `approve`. `NullCodeHost` no escribe en ningún sitio externo.

## Testing (TDD, sin BD/LLM/GitHub salvo integración del repo)
- **Actuadores** (puros/mockeados): `QuarantineActuator` (flaky → ticket de deuda **no vacío** + anotación; el invariante); `TicketActuator` con `RootCauseAnalyzer` mockeado (real → body con root-cause+linaje; analyzer que lanza → degrada a "no disponible").
- **`ActionService`** (repo + actuadores mockeados): mapeo categoría→actuador; `skipped` para maintenance/infra/unknown; `propose_actions` persiste lo correcto; `approve_action` materializa vía CodeHost (stub) + sign-off; idempotencia.
- **Endpoints** (servicio mockeado): propose/inbox/approve/reject; 401; 502.
- **Repo** (integración Postgres): CRUD de `actions` + idempotencia + no-miembro + `run_id` ajeno → rechazado.

## Fases (tareas del plan)
1. Migración `010_actions.sql`.
2. `base.py` (`ActionProposal`, `Actuator`, `CodeHost`, `NullCodeHost`) — puro.
3. `quarantine.py` (`QuarantineActuator`) + tests.
4. `ticket.py` (`TicketActuator`, reusa `RootCauseAnalyzer`/linaje, degradante) + tests.
5. Repo: `save_actions`/`get_actions`/`approve_action`/`reject_action` + tests integración.
6. `service.py` (`ActionService`) + tests con mocks.
7. Endpoints `/v2/actions*` + wiring + tests.

## Fuera de alcance (YAGNI / fases posteriores)
- **Self-heal del locator** (candidatos DOM + diff LLM) → **F3b**.
- **GitHub App real** (PR borrador / Issue de verdad; auth) → **F3c**.
- **Lazo de aprendizaje** al aprobar/rechazar (p. ej. `set_family_label`, penalizar estrategia) → **F5**. En F3a `approve`/`reject` solo cambian estado + sign-off.
- **Gate en CI + certificado** → **F4**.
- Anotación de cuarentena como PR real (en F3a es contenido propuesto en el `payload`; el PR se materializa en F3c).
