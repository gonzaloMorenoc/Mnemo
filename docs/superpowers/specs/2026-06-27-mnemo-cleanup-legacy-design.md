# Mnemo — Limpieza del legacy Smart Error Debugger + README (diseño)

**Fecha:** 2026-06-27 · **Origen:** petición del usuario ("actualizar el README y eliminar todo lo referente al smarterrordebugger") + follow-up de la auditoría/H2 · **Base:** `main` 07d28a5 · **Backend:** Python.

## Objetivo

Eliminar el RAG v1 legacy (Smart Error Debugger) del repo y dejar el README/docs solo sobre Mnemo Autopilot — **desacoplando primero** las dos piezas que el v2 todavía usa, para no romper nada.

## Decisiones (confirmadas)

- **Borrado COMPLETO (git rm)** del RAG v1 (el historial de git lo conserva).
- **Eliminar también el ADR del pivote** (`docs/adr/0001-pivote-a-mnemo.md`).
- **Migrar** el endpoint `POST /v2/defects/{id}/root-cause` a `RootCauseAnalyzer` (B2) — se mantiene la función, sin el analyzer legacy.
- **Extraer** la CRUD de orgs de `tenant_kb` a `src/orgs/repository.py`.
- **NO tocar** `src/sanitizer.py` ni `src/config.py` (los usa el v2). **NO tocar** los registros de proceso (`docs/superpowers/*`, `docs/auditoria/*`) — son historia del proyecto, no del producto legacy.
- Cada fase deja `pytest -m "not integration"` y el frontend (`npm test`) verdes. `DATABASE_URL`=prod. Commits con `Claude-Session`.

## Grafo verificado (qué importa qué)

- **RAG v1 puro** (solo lo importan `main.py`/`ui.py`/`api.py` y entre sí): `loader`, `vector_store`, `model` (→`retriever`,`prompts`), `retriever`, `prompts`, `evaluator`, `history`, `inspector`.
- **`scope_priority`**: solo `tenant_kb` (legacy) + `test_scope_priority`/`test_imports`.
- **Acoplados al v2** (a desacoplar): `structured_analyzer` (← `api_v2` endpoint root-cause), `tenant_kb` (← `api_v2` orgs + `test_api_v2`).
- **Compartidos (se quedan):** `sanitizer` (defects/ci/jira ingestion), `config`.

## Fase 1 — Desacople (el v2 deja de tocar el legacy)

### 1a. Endpoint root-cause → `RootCauseAnalyzer`
En `src/api_v2.py`, `root_cause_v2` usa hoy `analyzer: StructuredAnalyzer = Depends(get_analyzer)` con `analyzer.analyze_structured(family, failures)` + `analyzer.analyze(...)`. `RootCauseAnalyzer` (B2, `src/assurance/root_cause.py`) expone la MISMA interfaz y ya está cableado vía `_LazyRootCauseAnalyzer`/`get_root_cause_analyzer`. Cambiar la dependencia del endpoint a ese analyzer; eliminar `get_analyzer` y el import de `StructuredAnalyzer`. Verificar con el test del endpoint (`tests/test_api_v2_root_cause.py`, de B2) que el comportamiento (gate degradado→503, cache, save) se mantiene.

### 1b. Orgs → `src/orgs/repository.py`
Crear `src/orgs/__init__.py` + `src/orgs/repository.py` con `OrganizationRepository` que tenga **exactamente** `create_organization(*, user_id, name)`, `join_organization(*, user_id, join_code)`, `list_user_organizations(*, user_id)` — copiadas de `TenantKBRepository` (mismo SQL/firmas; sin la parte RAG). `src/api_v2.py` `get_repo` devuelve `OrganizationRepository`; actualizar los 3 endpoints `/v2/orgs` y los tipos. Actualizar `tests/test_api_v2.py` para apuntar a `OrganizationRepository`.

## Fase 2 — Borrado del RAG v1

`git rm`: `main.py`, `ui.py`, `api.py`; `src/loader.py`, `src/vector_store.py`, `src/model.py`, `src/retriever.py`, `src/prompts.py`, `src/evaluator.py`, `src/history.py`, `src/inspector.py`, `src/structured_analyzer.py`, `src/scope_priority.py`, `src/tenant_kb.py`; los tests legacy (`tests/test_evaluation.py`, `tests/test_scope_priority.py`, y cualquier otro que solo cubra los anteriores); el dir `legacy/`. En el `Dockerfile`, quitar `COPY api.py .`. Actualizar `tests/test_imports.py` (quitar `tenant_kb`/`structured_analyzer`/`scope_priority`; mantener `security`/`multitenant_models`/`sanitizer`; añadir `src.orgs.repository`). Tras borrar: `grep -rn "src\.\(loader\|vector_store\|model\|retriever\|prompts\|evaluator\|history\|inspector\|structured_analyzer\|scope_priority\|tenant_kb\)" src/ tests/` debe salir vacío.

## Fase 3 — README + docs de producto

- **README.md**: quitar la nota "Evolución de SmartErrorDebugger…" y cualquier mención; dejar el README solo sobre Mnemo (ya está casi todo así).
- **`.env.example`**: `LANGCHAIN_PROJECT` deja de ser `"SmartErrorDebugger"` (→ `"Mnemo"` o quitarlo).
- **`docs/functional/overview.md`**, **`doc/AUDITORIA_CONCURSO_MTP.md`**, **`src/__init__.py`** (docstring si aplica): quitar las menciones a SmartErrorDebugger.
- **Borrar** `docs/adr/0001-pivote-a-mnemo.md`.
- NO tocar `docs/superpowers/*` ni `docs/auditoria/*` (registros de proceso). Tras la fase: `grep -ril "smarterrordebugger\|smart error debugger" --include='*.md' --include='*.py' --include='*.ts*' .` (excluyendo node_modules + docs/superpowers + docs/auditoria) debe salir vacío; reportar lo que quede en los registros de proceso (intencional).

## Garantías

- **Sin regresión:** F1 mantiene el endpoint root-cause + los endpoints de orgs idénticos (mismas firmas/SQL); los tests existentes pasan apuntados a los módulos nuevos.
- **Verde en cada fase:** `pytest -m "not integration"` + `npm test` (frontend) tras cada fase.
- **Reversible:** el código borrado vive en el historial de git.

## Testing

- F1: `test_api_v2_root_cause.py` (root-cause migrado) + `test_api_v2.py` (orgs → OrganizationRepository) pasan; si hay test de integración de orgs, sigue verde.
- F2: la suite pasa sin los módulos borrados; `test_imports.py` actualizado importa los módulos vivos (incl. `src.orgs.repository`).
- F3: el grep de SmartErrorDebugger queda vacío fuera de los registros de proceso.

## Fuera de alcance

- Bloque C (C3 PDF, C4 guion) — independiente.
- Partir los God-objects (`api_v2.py`, `defects/repository.py`) — limpieza distinta.
- Reescribir la historia de git (los archivos quedan en commits pasados, intencional).
