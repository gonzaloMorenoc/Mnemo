# Mnemo Autopilot — F3c-2: self_heal → PR borrador real (diseño)

**Fecha:** 2026-06-24 · **Fase:** F3c-2 (cuarta de F3, §6.1 del spec maestro) · **Rama:** `feat/mnemo-selfheal-pr` (apilada sobre `feat/mnemo-github-app`/PR #17; reapuntar a `main` cuando F3c mergee)

## Objetivo

Al aprobar una acción de **self_heal**, abrir un **PR borrador real** en GitHub que **cura el locator roto**: localiza el archivo del test, reemplaza el `broken_locator` por el `suggested_locator` (determinista, de F3b) y abre el PR (`draft=true`) con la evidencia. Implementa `GitHubCodeHost.open_draft_pr` (que F3c dejó como `NotImplementedError`) y persiste el `file` del test en la ingesta. Nivel 2: nunca auto-merge.

## Decisiones (confirmadas)

- **Edit determinista (string-replace) + degrada.** El CodeHost lee el archivo (contents API), hace `content.replace(broken_locator, suggested_locator, 1)`; si no casa exactamente → degrada (no abre PR). Sin LLM en el camino del diff (clave para el certificado de F4). El formato canónico de F3b (comillas simples, `{ name: '...' }`) casa con el código estándar de Playwright; si difiere, degrada (LLM-fallback = roadmap).
- **Persistir `file` (+`line`) en la ingesta.** El reporter ya emite `file`/`line` (`CiTestResult`) pero `to_failure_records` los descarta. Se persisten en `failures` y se exponen vía `get_selfheal_context` → payload de self_heal.
- **Idempotencia por branch determinista** `mnemo/self-heal/{action_id}`: antes de crear, buscar PR por `head` → reusar si existe (más fiable que el índice de search). Marcador en el body como secundario.
- **Base del PR:** la rama default del repo (HEAD actual), no el `commit_sha` del run.
- **Reúso de F3c:** `GitHubAppAuth` (installation token), `GitHubCodeHost`, `codehost_factory(org_id, user_id)`, materialización segura (`approve→materialize`).

## Componentes

### Persistencia de `file`/`line` (cadena de ingesta) — migración `012_failure_location.sql`
- `failures`: `add column if not exists file text` + `add column if not exists line int` (nullable).
- `FailureRecord` (`src/ingest/models.py`): `+ file: Optional[str]`, `+ line: Optional[int]`.
- `to_failure_records` (`src/ci/mapping.py`): pasar `t.file`, `t.line`.
- INSERT de `failures` (`src/defects/repository.py`): añadir las columnas `file`, `line`.
- `get_selfheal_context` (`src/defects/repository.py`): añadir `f.file` al SELECT y `"file": row["file"]` al dict de retorno.
- `SelfHealActuator.propose` (`src/actions/selfheal/selfheal.py`): `payload["file"] = context.get("file")`.

### `src/actions/base.py` — `CodeHost`/`NullCodeHost`
`open_draft_pr` cambia de `(*, title, body, patch)` a **`(*, title, body, file_path, old_str, new_str, marker="") -> Optional[str]`** (URL del PR, o `None` si el locator no casa → degrada). `NullCodeHost.open_draft_pr` devuelve `"stub://pr/pending"`.

### `src/ci/github_app.py` — `GitHubCodeHost.open_draft_pr`
Implementa el flujo (reemplaza el `NotImplementedError`), con `requests` + `_headers()` (token de F3c):
1. `branch = f"mnemo/self-heal/{<action_id del marker>}"` — determinista. GET `pulls?head={owner}:{branch}&state=all`; si existe → devuelve su `html_url` (idempotencia).
2. GET `/repos/{repo}` → `default_branch`; GET `/repos/{repo}/git/ref/heads/{default}` → `sha` base.
3. GET `/repos/{repo}/contents/{file_path}?ref={default}` → contenido (base64 → texto) + `file_sha`.
4. `new_content = content.replace(old_str, new_str, 1)`; si `new_content == content` → devuelve **`None`** (locator no encontrado → no es un error de GitHub; el service degrada en silencio). `GitHubError` se reserva para errores reales de la API.
5. POST `/repos/{repo}/git/refs` (`ref=refs/heads/{branch}`, `sha`); 422 "ya existe" → reusa el branch.
6. PUT `/repos/{repo}/contents/{file_path}` (`message`, `content=base64(new_content)`, `sha=file_sha`, `branch`) → commit.
7. POST `/repos/{repo}/pulls` (`title`, `body` + `<!-- {marker} -->`, `head=branch`, `base=default`, `draft=true`) → `html_url`.

El `action_id` para el branch se deriva del `marker` (`mnemo:action:{id}`) que pasa el service, manteniendo la firma genérica.

### `src/actions/service.py` — `ActionService`
- La rama `if kind == "self_heal"` de `approve_action` **deja de hacer short-circuit**; llama a `_materialize_self_heal(action, codehost)`.
- `_materialize_self_heal`: `payload = action["payload"]`; si `payload.get("file")` es `None` → degrada (no materializa: devuelve `materialized=False`, `logger.warning`). Si hay `file`:
  `ref = codehost.open_draft_pr(title=summary, body=<broken→suggested + reasoning + candidatos>, file_path=payload["file"], old_str=payload["broken_locator"], new_str=payload["suggested_locator"], marker=f"mnemo:action:{action['id']}")` → `materialize_action(artifact_ref=ref)`.

## Garantías

- **Determinista y auditable:** locator (F3b) + diff (string-replace exacto) sin LLM.
- **Idempotente:** branch por `action_id`; reintentar no duplica el PR.
- **Nivel 2:** solo PR `draft` tras un `approve` válido; nunca auto-merge.
- **Aislamiento por-org:** repo destino = el del org (config de F3c); membership ya validado en `get_action`.

## Manejo de errores / degradación

- `file` ausente (ingesta previa a F3c-2 / sin file) o `broken_locator` no presente en el archivo → **degrada**: la acción queda `approved` (materialized:False) + `logger.warning`; reintentable. No abre PR vacío ni Issue de fallback (YAGNI).
- GitHub API 4xx/5xx → `GitHubError` → 502 (acción `approved`, reintentable).
- App no configurada en env → 503; org sin integración GitHub → 400.

## Testing (TDD; `requests` mockeado, sin GitHub real)

- **`open_draft_pr`** (mocks de session): flujo completo (repo→ref→contents→replace→create-ref→put→pull) devuelve la URL del PR; **idempotencia** (PR por `head` ya existe → reusa, no crea); locator no casa (`replace` no cambia nada) → `GitHubError`; branch ya existe (422) → continúa.
- **Persistencia `file`/`line`** (integración Postgres): `ingest_ci_run` guarda `file`/`line`; `get_selfheal_context` devuelve `file`.
- **`SelfHealActuator`**: el payload incluye `file` cuando el contexto lo trae.
- **`ActionService`**: approve de `self_heal` con `file` → `open_draft_pr` con `file`/old/new/marker correctos y `materialize_action`; `file=None` → degrada (`materialized=False`, sin llamar al codehost).
- **Endpoint**: approve de `self_heal` materializa un PR (artifact_ref = url); GitHubError → 502.

## Fases (tareas del plan)

1. Migración `012` + `FailureRecord`/`to_failure_records` + INSERT `failures` + `get_selfheal_context` (file) + payload `SelfHealActuator` (file) + tests (unit mapping + integración ingest/selfheal_context).
2. `open_draft_pr` en `CodeHost`/`NullCodeHost` (firma nueva) + `GitHubCodeHost.open_draft_pr` (flujo refs/contents/pulls + replace + idempotencia) + tests con `requests` mockeado.
3. `ActionService._materialize_self_heal` + cableado de `approve_action` (self_heal materializa; degrada si falta file) + tests; verificación de endpoint (approve self_heal → PR).

## Fuera de alcance (YAGNI / fases posteriores)

- Multi-archivo / Page Objects; LLM-fallback para el edit cuando el formato difiere; normalización de comillas/espacios del locator.
- Sincronizar el estado del PR (merged/closed) vía webhook entrante → roadmap (alimenta el lazo de F5).
- Check runs / gate + certificado → **F4**.
