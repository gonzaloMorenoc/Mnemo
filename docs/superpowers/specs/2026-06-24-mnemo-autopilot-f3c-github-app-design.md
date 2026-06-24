# Mnemo Autopilot — F3c: GitHub App + materialización real de Issues (diseño)

**Fecha:** 2026-06-24 · **Fase:** F3c (tercera de F3, §6.5 del spec maestro) · **Rama:** `feat/mnemo-github-app` (desde `main`; F3a/F3b ya mergeadas)

## Objetivo

Reemplazar `NullCodeHost` por un **`CodeHost` real** que, al aprobar una acción, **materialice un Issue de GitHub** (defecto real → ticket enriquecido; flaky → cuarentena con deuda). La materialización es **segura** (no deja Issues huérfanos ni duplicados ante fallos/concurrencia) y se extrae `ActionRepository` de `repository.py` (>800 líneas). El **self_heal→PR con diff real** y los **check runs (gate)** quedan fuera (F3c‑2 / F4).

## Decisiones (confirmadas)

- **Alcance:** plumbing (App + config por-org) + **Issues** reales + materialización segura + `ActionRepository`. `self_heal` al aprobarse queda `approved` **sin materializar** (su PR es F3c‑2); check runs → F4.
- **Auth: una GitHub App global + instalación por-org.** Las credenciales de la App (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` PEM) viven en **env** (globales); cada org guarda su `installation_id` + `repo_full_name` (`owner/repo`). JWT RS256 (`pyjwt`) → **installation access token** efímero (cache ~55 min) → API REST con `requests` (el repo no usa httpx).
- **Materialización: estados `proposed → approved → materialized` + marcador idempotente.** `approve` hace el UPDATE atómico (solo si `proposed`) y registra el sign-off **sin** llamar a GitHub; luego `materialize` crea el Issue con un marcador oculto `<!-- mnemo:action:{action_id} -->` y, **antes de crear, lo busca** para reusar en vez de duplicar. Si GitHub falla, la acción queda `approved` (decisión preservada) y es **reintentable** sin duplicar.
- **CodeHost por-org, no singleton:** `ActionService` recibe un **`codehost_factory: Callable[[org_id], CodeHost]`** (default → `NullCodeHost`, conserva el comportamiento de F3a y los tests).
- **Reúso del patrón de integraciones** (`org_integrations`, membership-gated) ya usado por Jira; sin secreto por-org (la private key es global), así que no se cifra nada nuevo.

## Componentes (archivos pequeños, <400 líneas)

### `src/ci/github_auth.py` — `GitHubAppAuth`
- `app_jwt() -> str`: JWT RS256 con `iss=GITHUB_APP_ID`, `iat`/`exp` (≤10 min), firmado con la private key de env.
- `installation_token(installation_id) -> str`: `POST /app/installations/{id}/access_tokens` con el JWT; **cachea** el token por `installation_id` hasta poco antes de expirar.
- Errores (clave/credenciales ausentes o inválidas, 4xx/5xx) → `GitHubAuthError`. Construcción **perezosa**: una mala config no debe tumbar el arranque.

### `src/ci/github_app.py` — `GitHubCodeHost(CodeHost)`
- Construido con `(auth, installation_id, repo_full_name)`.
- `create_issue(*, title, body, labels, marker) -> str`: **busca** un Issue existente con el marcador (`GET /search/issues?q=repo:owner/name+in:body+"mnemo:action:{id}"`); si existe → devuelve su `html_url`; si no → `POST /repos/{owner}/{repo}/issues` con el marcador anexado al body → `html_url`.
- `open_draft_pr(...)` → `NotImplementedError` ("F3c‑2"). Errores de la API → `GitHubError`.

### `src/actions/repository.py` — `ActionRepository`
Extrae de `AssuranceRepository` el CRUD de acciones y **divide** el antiguo `approve_action`:
- `save_actions`, `get_actions`, `get_action` (ahora **devuelve `org_id`**), `reject_action` (sin cambios de semántica).
- `approve_action(*, user_id, action_id) -> bool`: UPDATE atómico `proposed → approved` + `approved_by`/`approved_at` (solo si `proposed`, membership-gated).
- `materialize_action(*, user_id, action_id, artifact_ref) -> bool`: UPDATE atómico `approved → materialized` + `artifact_ref` (solo si `approved`).
- Las lecturas de contexto de triaje (`get_run_actionable_verdicts`, `get_family_with_failures`, `get_selfheal_context`) **permanecen** en `AssuranceRepository`.

### `src/actions/service.py` — `ActionService` (cambios)
- Constructor recibe `codehost_factory` (default → `NullCodeHost`) en vez de un `codehost` fijo.
- `approve_action(*, user_id, action_id)`:
  1. `get_action`: si no existe o `rejected` → `{approved: False}`. Si ya `materialized` → **idempotente**: `{approved: True, materialized: True, artifact_ref: <existente>}` (no recrea). Si `proposed`/`approved` → continúa (`approved` = materialización pendiente de un intento previo).
  2. Si `proposed`: `repo.approve_action` (atómico). Si rowcount 0 → relee (otro ganó la carrera).
  3. Si `kind == "self_heal"` → no materializa: devuelve `{approved: True, materialized: False, artifact_ref: None}` (PR real en F3c‑2).
  4. `codehost = codehost_factory(action["org_id"])`; `ref = codehost.create_issue(..., marker=action_id)`.
  5. `repo.materialize_action(artifact_ref=ref)`.
  6. `{approved: True, materialized: True, artifact_ref: ref}`.

## Datos — migración `011_github_integration.sql`

- `org_integrations`: añadir `installation_id text` y `repo_full_name text` (nullable; solo `provider='github'` los usa). Sin secreto por-org (la private key es global) → no se usa `api_token_enc`.
- `actions`: añadir la FK que faltaba `approved_by → auth.users(id) on delete set null` (hallazgo de la revisión de F3a).

## Endpoints (`/v2`, `Depends(get_current_user)`)

| Método | Ruta | Notas |
|---|---|---|
| POST | `/v2/integrations/github` | guarda `installation_id` + `repo_full_name` (membership-gated) |
| GET | `/v2/integrations/github` | estado de la config (`{configured, repo_full_name}`) |
| POST | `/v2/actions/{id}/approve` | **ahora materializa de verdad** (antes `NullCodeHost`) |

`get_action_service` construye `ActionService` con un `codehost_factory` que lee `org_integrations` del org y arma `GitHubCodeHost` con `GitHubAppAuth` (env), perezosamente. En `GET /v2/actions` se valida `status` contra whitelist (`proposed|approved|rejected|materialized` → 400 si no) — otro hallazgo de F3a.

## Manejo de errores

- Sin auth → 401 · no miembro → vacío/`PermissionError` según método.
- Org sin integración GitHub → **400** ("GitHub no configurado para el org").
- App no configurada en env (sin `GITHUB_APP_ID`/clave) → **503** (perezoso, no tumba el arranque; patrón `_LazyRootCauseAnalyzer`).
- GitHub API 4xx/5xx o auth → **502**; la acción queda `approved` (reintentable, idempotente por marcador).
- BD → 502. **Nivel 2 intacto:** solo se materializa una acción que pasó por un `approve` válido.

## Testing (TDD; `requests` mockeado, sin GitHub real)

- **`github_auth`**: JWT con claims correctos (`iss`, `exp`); intercambio → installation token; cache reutiliza; errores → `GitHubAuthError`.
- **`github_app`**: `create_issue` crea con el marcador; si la búsqueda encuentra el marcador → **reusa** (no duplica); 4xx/5xx → `GitHubError`.
- **`service.approve_action`** (codehost+repo mockeados): `proposed→approved→materialized`; **idempotencia** (segundo approve no crea otro Issue); GitHub falla → queda `approved`, reintento materializa; `self_heal` → `approved` sin materializar.
- **`ActionRepository`** (integración Postgres): transiciones atómicas (`approve` solo si `proposed`; `materialize` solo si `approved`), aislamiento no-miembro, migración 011.
- **Endpoints**: 401 sin auth · 400 sin integración GitHub · 502 GitHub/BD · `integrations/github` upsert+get membership-gated · `status` inválido → 400.

## Fases (tareas del plan)

1. Migración `011` (org_integrations github + FK `approved_by`) + `GitHubConfig` en `IntegrationsRepository` (upsert/get) + endpoints `/v2/integrations/github` + tests.
2. `src/ci/github_auth.py` (`GitHubAppAuth`: JWT + installation token + cache + errores) + tests.
3. `src/ci/github_app.py` (`GitHubCodeHost.create_issue` con marcador idempotente; `open_draft_pr` → NotImplemented) + tests.
4. Extraer `ActionRepository` (CRUD + `approve_action`/`materialize_action` divididos; `get_action` con `org_id`) + tests de regresión.
5. `ActionService` con `codehost_factory` + flujo `approve→materialize` (self_heal queda approved) + tests.
6. Wiring en `api_v2` (`get_action_service` con factory real perezoso; approve materializa; whitelist de `status`) + tests de endpoint.

## Fuera de alcance (YAGNI / fases posteriores)

- **`self_heal → PR` con diff real**: persistir `file`/`line` en el ingest, leer/editar el archivo del test vía contents API, branch+commit+PR → **F3c‑2**.
- **Check runs / gate** y **Release Assurance Certificate** → **F4**.
- **Webhook entrante de GitHub** para sincronizar el estado de Issues/PRs (merged/closed) → roadmap (alimenta el lazo de F5).
- Jira/Azure como sinks (interfaz `CodeHost` ya lo permite) → roadmap.
