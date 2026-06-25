# Mnemo Autopilot — Tanda 1: hardening de seguridad y correctitud (diseño)

**Fecha:** 2026-06-26 · **Origen:** auditoría `docs/auditoria/2026-06-25-auditoria-profunda.md` (bloqueantes B1-B3 + altos A1-A4, A6/A8/A9) · **Ramas:** `feat/mnemo-hardening-data` (PR-A) y `feat/mnemo-hardening-actions` (PR-B), ambas desde `main`

## Objetivo

Cerrar los bloqueantes y los altos de seguridad/correctitud que la auditoría identificó antes de exponer Mnemo a clientes: aislamiento RLS completo, atomicidad de la materialización de acciones, idempotencia de ingesta, autorización por rol, anti-injection, y una métrica del foso honesta. Backend Python/FastAPI, multitenant. Dos PRs por área de código (sin solapes).

## Decisiones (confirmadas)

- **Agrupación: 2 PRs.** PR-A = migración 016 + correctitud de ingesta/triaje (`src/defects/repository.py`). PR-B = capa de acción endurecida (`src/actions/`, `src/ci/github_app.py`, `src/multitenant_models.py`). Independientes (áreas disjuntas), cualquier orden; PR-A primero por la migración crítica.
- **A1 (authz por rol):** reconfigurar integraciones (`upsert_github_config`/`upsert_jira_config`) exige **admin/owner**; aprobar/rechazar/materializar acciones queda en **member** (es el trabajo diario de QA).
- **B2 (atomicidad):** estado intermedio `materializing` + `SELECT … FOR UPDATE` / `UPDATE … WHERE status='approved'`.
- **A3 (métrica del foso):** `engine_category = "unknown" if llm_assisted else tv.category` (sin migración).
- `DATABASE_URL` del `.env` ES PRODUCCIÓN → la migración 016 se aplica con `psql`. main protegida (PRs). Invariante RLS. TDD por subagentes.

---

## PR-A — Migración 016 + correctitud de ingesta/triaje

### B1 + A6 + A8 + A9 — `db/migrations/016_hardening.sql`
- **B1 (force RLS):** `alter table … force row level security` en las 7 tablas de 001: `profiles, organizations, memberships, documents, chunks, embeddings, analyses`. Confirmar `enable` en `analyses` (añadirlo si falta). Idempotente.
- **A6 (índices FK):** `idx_triage_verdicts_failure (failure_id)`, `idx_actions_verdict (triage_verdict_id)`, `idx_triage_corrections_family (family_id)`, `idx_test_runs_commit (org_id, project, commit_sha) where commit_sha is not null`, `idx_certificates_org (org_id)`.
- **A8 (hoist):** `create or replace function public.is_org_member(target_org_id uuid) … select exists(select 1 from public.memberships m where m.org_id = target_org_id and m.user_id = (select auth.uid()))` (la subconsulta permite hoisting per-query).
- **A9 (ivfflat parciales):** recrear los índices ivfflat de `failures.embedding` (002) y `defect_families.centroid` (003) como `… where embedding/centroid is not null` (drop + create concurrently no aplica dentro de migración transaccional; usar drop + create normal).
- **Aplicar:** `set -a && source .env && set +a && psql "$DATABASE_URL" -f db/migrations/016_hardening.sql` (Bash con `dangerouslyDisableSandbox`). **Verificar:** `select relname, relrowsecurity, relforcerowsecurity from pg_class where relnamespace='public'::regnamespace and relkind='r' order by relname;` → todas `t,t`.

### B3 — dedup de ingesta idempotente
`src/defects/repository.py` (`ingest_ci_run`, ~250-274): sustituir el patrón check-then-insert del `test_runs` por `INSERT INTO public.test_runs (…) VALUES (…) ON CONFLICT (org_id, run_uid) DO NOTHING RETURNING id`. Si no devuelve fila (conflicto), hacer `SELECT id FROM test_runs WHERE org_id=%s AND run_uid=%s` y retornar `{run_id, deduplicated: True}`. Elimina la `UniqueViolation`→502 en entregas concurrentes.

### A3 — `engine_category` honesto en el lazo
`src/defects/repository.py` (`set_family_label`, ~845): la query que obtiene el veredicto más reciente de la familia debe traer también `tv.llm_assisted`; calcular `engine_category = "unknown" if row["llm_assisted"] else row["category"]` antes de insertar en `triage_corrections`. Así `get_calibration_metrics` (que compara `engine_category == human_category`) mide la precisión del **motor determinista**, no la del LLM. (El motor que cede al LLM fue ambiguo → no debe contar como acierto.)

### A4 — sin familia duplicada por centroid NULL
`src/defects/repository.py` (`_query_candidates`, ~72-88): en la rama de coincidencia por firma exacta (`signature = %(fp)s`), **no** incluir el filtro `centroid is not null` (solo la rama de top-K por coseno lo necesita). Evita que una familia con firma exacta y centroide nulo quede invisible → se cree otra con la misma `signature` → `UniqueViolation` que aborta toda la ingesta del run.

---

## PR-B — Capa de acción endurecida

### A1 — authz por rol en reconfiguración de integraciones
`src/jira/integrations_repository.py`: añadir un check de rol admin/owner en `upsert_github_config` y `upsert_jira_config` (p. ej. un helper `_require_admin(cur, org_id, user_id)` que lance `PermissionError` si `not exists(select 1 from memberships where org_id=%s and user_id=%s and role in ('owner','admin'))`). Los endpoints ya mapean `PermissionError → 403`. `approve/materialize/reject_action` NO cambian (quedan member).

### B2 — atomicidad approve → materialize
`src/actions/repository.py` + `src/actions/service.py`:
- Añadir transición atómica `approved → materializing`: `UPDATE actions SET status='materializing' WHERE id=%s AND status='approved' RETURNING …` (o `SELECT … FOR UPDATE` sobre la fila approved). Si `rowcount==0`, otra request ya la tomó → no materializar (evita doble-materialización concurrente, H4).
- `materialize_action` (materializing → materialized) persiste `artifact_ref` en la misma transacción que el cambio de estado final. Si la creación del artefacto en GitHub falla tras pasar a `materializing`, revertir a `approved` (o dejar `materializing` + log para reconciliación) — no perder el progreso.
- El marcador idempotente (`_find_by_marker`/`_find_pr_by_head`) queda como **reconciliación** (red de seguridad), no como mecanismo primario.
- `_ACTION_STATUSES` (api_v2) y cualquier validación de estado deben incluir `materializing`.

### A2 — anti-injection en la GitHub API
- `src/multitenant_models.py` (`GitHubConfigRequest`): validador Pydantic de `repo_full_name` con `pattern=r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$"` (o `field_validator`).
- `src/ci/github_app.py`: `urllib.parse.quote(file_path, safe="/")` antes de interpolar `file_path` en las URLs de `contents`. (El `repo_full_name` ya validado en el borde; defensa en profundidad.)

---

## Testing (TDD)

- **PR-A:** migración aplicada + verificación RLS (integración: `relforcerowsecurity` en las 7 tablas); dedup concurrente (dos `ingest_ci_run` con el mismo `run_uid` → uno inserta, el otro `deduplicated=True`, sin 502/excepción); `set_family_label` registra `engine_category=unknown` cuando el veredicto fue `llm_assisted=True` y `tv.category` cuando no (integración, SELECT de vuelta sobre `triage_corrections` — cierra también el gap M7 de aserción); `_query_candidates`/`decide_match` devuelve la familia de firma exacta aunque `centroid` sea NULL (no crea duplicado).
- **PR-B:** `upsert_github_config`/`upsert_jira_config` rechaza a un `member` (no admin) con `PermissionError`/403 y acepta a un admin; un `member` SÍ puede approve/reject (sin regresión); la atomicidad (`approved→materializing`: dos approve concurrentes → un solo materialize; fallo de GitHub tras materializing → no queda materialized con artifact_ref perdido); `GitHubConfigRequest` rechaza `repo_full_name` inválido (422); `file_path` con caracteres especiales se url-encoda.

## Fuera de alcance (otras tandas)

- Tanda 2 (robustez/perf no crítica): N+1 `executemany` (A7), HNSW, `get_calibration_metrics` en 1 query, integración fuera de prod (M6), rate limiting (M12), limpieza `history.db`/`MNEMO_SECRET_KEY` (M10/M11).
- Tanda 3 (demo del concurso) · Tanda 4 (refactors arquitectura M1-M3).
