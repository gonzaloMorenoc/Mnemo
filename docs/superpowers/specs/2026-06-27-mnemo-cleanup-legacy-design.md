# Mnemo — Limpieza del legacy Smart Error Debugger + README (diseño)

**Fecha:** 2026-06-27 (corregido tras recon) · **Origen:** petición del usuario ("actualizar el README y eliminar todo lo referente al smarterrordebugger") + follow-up auditoría/H2 · **Base:** `main` 07d28a5 · **Backend:** Python · **Frontend:** Next.js/TS.

## Objetivo

Eliminar TODO el Smart Error Debugger (el "analizador de errores" RAG v1 y su UI) y dejar Mnemo **solo como Autopilot** (ingesta → triaje → acción → certificado → briefing), desacoplando primero lo que el v2 reutiliza.

## Corrección del recon (importante)

- **`root_cause_v2` (POST /v2/defects/{id}/root-cause) YA está migrado** a `RootCauseAnalyzer` (B2, `Depends(get_root_cause_analyzer)`). NO se toca.
- **El acople real del legacy es `/v2/analyze`** (`analyze_v2`): pega un `error_log` → `StructuredAnalyzer.analyze` + `TenantKBRepository.retrieve_context`/`save_analysis` (RAG). Es Smart Error Debugger expuesto en v2, **con UI completa** (`app/analyze`, `components/analyze`, `api/v2/analyze/route.ts`, `analyzeError`, tipos `AnalyzeV2`).

## Decisiones (confirmadas)

- **Eliminar `/v2/analyze` y toda su UI** (decisión del usuario: limpieza total).
- **Borrado COMPLETO (git rm)** del RAG v1; el historial de git lo conserva.
- **Eliminar el ADR del pivote** (`docs/adr/0001-pivote-a-mnemo.md`).
- **Extraer** la CRUD de orgs de `tenant_kb` → `src/orgs/repository.py`; el resto de `tenant_kb` (RAG: `retrieve_context`/`save_analysis`/KB) se borra con `/v2/analyze`.
- **NO tocar** `src/sanitizer.py`, `src/config.py` (los usa el v2). **NO tocar** `docs/superpowers/*` ni `docs/auditoria/*` (registros de proceso).
- Cada fase: `pytest -m "not integration"` + `npm test` (frontend) verdes. Commits con `Claude-Session`.

## Grafo verificado

- **RAG v1 puro** (solo `main`/`ui`/`api` + entre sí): `loader`, `vector_store`, `model`(→`retriever`,`prompts`), `retriever`, `prompts`, `evaluator`, `history`, `inspector`.
- **`scope_priority`**: solo `tenant_kb` + tests.
- **`structured_analyzer`**: solo `/v2/analyze` (`analyze_v2`).
- **`tenant_kb`**: orgs (a extraer) + RAG (`retrieve_context`/`save_analysis`/KB, a borrar con `/v2/analyze`).
- **Compartidos (se quedan):** `sanitizer`, `config`.

## Fase 1 — Extraer la CRUD de orgs

Crear `src/orgs/__init__.py` + `src/orgs/repository.py` con `OrganizationRepository` que tenga **exactamente** `create_organization(*, user_id, name)`, `join_organization(*, user_id, join_code)`, `list_user_organizations(*, user_id)` — copiadas de `TenantKBRepository` (mismo SQL/`_connect`/`_set_claims`, sin la parte RAG). En `src/api_v2.py`: `get_repo` devuelve `OrganizationRepository`; los 3 endpoints `/v2/orgs` (`list_orgs`/`create_org`/`join_org`) y sus type hints pasan a `OrganizationRepository`. Actualizar `tests/test_api_v2.py` (orgs → `OrganizationRepository`). pytest verde.

## Fase 2 — Eliminar `/v2/analyze` (backend + frontend) + RAG v1

### Backend
- `src/api_v2.py`: eliminar el endpoint `analyze_v2` (`@router.post("/analyze")`), `get_analyzer`, el import de `StructuredAnalyzer`, y el import de `TenantKBRepository` (ya no usado tras F1). Quitar `_analyzer` global.
- `src/multitenant_models.py`: eliminar `AnalyzeV2Request`/`AnalyzeV2Response` (confirmar con grep que nada más los usa).
- `git rm`: `main.py`, `ui.py`, `api.py`; `src/{loader,vector_store,model,retriever,prompts,evaluator,history,inspector,structured_analyzer,scope_priority,tenant_kb}.py`; tests legacy (`tests/test_evaluation.py`, `tests/test_scope_priority.py`, y cualquiera que solo cubra los borrados); el dir `legacy/`.
- `Dockerfile`: quitar `COPY api.py .`.
- `tests/test_imports.py`: quitar `tenant_kb`/`structured_analyzer`/`scope_priority`; mantener `security`/`multitenant_models`/`sanitizer`; añadir `src.orgs.repository`.
- Verificación: `grep -rn "src\.\(loader\|vector_store\|model\|retriever\|prompts\|evaluator\|history\|inspector\|structured_analyzer\|scope_priority\|tenant_kb\)\|get_analyzer\|StructuredAnalyzer\|AnalyzeV2" src/ tests/` → vacío.

### Frontend
- `git rm`: `frontend/src/app/app/analyze/` (page), `frontend/src/components/analyze/`, `frontend/src/app/api/v2/analyze/` (route).
- `frontend/src/lib/api/endpoints.ts`: quitar `analyzeError`. `types.ts`: quitar `AnalyzeV2Request`/`AnalyzeV2Response` (y `UploadResponse`/`analyzeError`-only types si quedan huérfanos — confirmar con grep).
- Quitar el enlace de navegación a `/app/analyze` si existe (buscar en `components/layout`/nav).
- Verificación: `grep -rn "analyze\|AnalyzeV2" frontend/src` no debe dejar referencias colgadas; `npm test` + `tsc --noEmit` limpios.

## Fase 3 — README + docs de producto

- `README.md`: quitar la nota "Evolución de SmartErrorDebugger…" + menciones; si lista `/v2/analyze` como feature, quitarlo.
- `.env.example`: `LANGCHAIN_PROJECT` deja de ser `"SmartErrorDebugger"`.
- `docs/functional/overview.md`, `doc/AUDITORIA_CONCURSO_MTP.md`, `src/__init__.py`: quitar menciones.
- **`git rm`** `docs/adr/0001-pivote-a-mnemo.md`.
- NO tocar `docs/superpowers/*` ni `docs/auditoria/*`. Verificación: `grep -ril "smarterrordebugger\|smart error debugger" .` (excluyendo node_modules, docs/superpowers, docs/auditoria) → vacío.

## Garantías

- **Sin regresión:** los endpoints de orgs quedan idénticos (mismas firmas/SQL, repo nuevo); el resto del Autopilot (triaje/acciones/cert/gate/briefing) no se toca; `root_cause_v2` intacto (ya migrado).
- **Verde en cada fase:** `pytest -m "not integration"` + `npm test`.
- **Reversible:** el código borrado vive en el historial de git.

## Testing

- F1: `test_api_v2.py` (orgs → `OrganizationRepository`) verde; integración de orgs si existe.
- F2: la suite pasa sin los módulos/endpoint borrados; `test_imports.py` importa los vivos (+ `src.orgs.repository`); frontend `npm test`+`tsc` verdes sin el analyze.
- F3: el grep de SmartErrorDebugger queda vacío fuera de los registros de proceso.

## Fuera de alcance

- Bloque C (C3/C4) — independiente.
- Partir los God-objects.
- Reescribir el historial de git.
