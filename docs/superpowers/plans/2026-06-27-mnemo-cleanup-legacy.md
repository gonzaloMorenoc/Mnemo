# Limpieza del legacy Smart Error Debugger — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar todo el Smart Error Debugger (RAG v1 + el endpoint `/v2/analyze` y su UI) y dejar Mnemo solo como Autopilot, extrayendo antes la CRUD de orgs que el v2 reutiliza.

**Architecture:** T1 extrae orgs (`tenant_kb`→`src/orgs/repository.py`). T2 borra `/v2/analyze` + el RAG v1 (backend). T3 borra el analyze del frontend. T4 limpia README/docs + borra el ADR.

**Tech Stack:** Python/FastAPI/pytest (backend); Next.js/TS/vitest (frontend).

## Global Constraints

- **Eliminar `/v2/analyze` y su UI; rm completo del RAG v1** (historial git lo conserva). **Borrar el ADR** del pivote.
- **`root_cause_v2` NO se toca** (ya migrado a RootCauseAnalyzer en B2). **`sanitizer`/`config` se quedan** (los usa el v2). **`docs/superpowers/*` y `docs/auditoria/*` NO se tocan** (registros de proceso).
- Cada tarea: backend `python3 -m pytest -m "not integration"` verde y/o frontend `npm test`+`tsc` verde, según lo que toque.
- Commits terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Extraer la CRUD de orgs a `src/orgs/repository.py`

**Files:** Create `src/orgs/__init__.py`, `src/orgs/repository.py`; Modify `src/api_v2.py`, `tests/test_api_v2.py`.

**Interfaces:** Produces — `OrganizationRepository(db_url=DATABASE_URL)` con `create_organization(*, user_id, name)`, `join_organization(*, user_id, join_code)`, `list_user_organizations(*, user_id)` (firmas idénticas a las de `TenantKBRepository`).

- [ ] **Step 1: Crear el módulo.** `src/orgs/__init__.py` vacío. `src/orgs/repository.py`: copia de `src/tenant_kb.py` la `class` (renombrada a `OrganizationRepository`), su `__init__`, `_connect`, y los métodos `create_organization`/`join_organization`/`list_user_organizations` (líneas ~40-115) **literalmente** (mismo SQL, mismos imports que necesiten: `psycopg`, `DATABASE_URL` de config, los row-factory/helpers que usen). NO copies métodos RAG (`retrieve_context`/`save_analysis`/etc.). Lee `src/tenant_kb.py:40-115` y trasládalo.

- [ ] **Step 2: Apuntar `api_v2` al nuevo repo.** En `src/api_v2.py`: añadir `from src.orgs.repository import OrganizationRepository`; cambiar `get_repo()` para que devuelva `OrganizationRepository` (`-> OrganizationRepository`, `_repo = OrganizationRepository()`); cambiar el type hint `repo: TenantKBRepository = Depends(get_repo)` por `repo: OrganizationRepository = Depends(get_repo)` en los 3 endpoints `/v2/orgs` (`list_orgs`, `create_org`, `join_org`). NO quites aún el import de `TenantKBRepository` (lo usa `analyze_v2`, que se borra en T2).

- [ ] **Step 3: Actualizar el test.** En `tests/test_api_v2.py`, donde se mockea/usa `TenantKBRepository` para los endpoints de orgs, apuntar a `OrganizationRepository` (mismo patrón de override/mock). (`analyze_v2`'s test, si existe aquí, lo elimina T2.)

- [ ] **Step 4: Test (integración del repo, opcional pero recomendado).** Si hay un test de integración de orgs (`grep -rln "create_organization\|join_organization\|list_user_organizations" tests/`), apúntalo a `OrganizationRepository`; si no, añade `tests/test_orgs_repository.py` mínimo que cree una org y la liste (con cleanup), reusando el patrón de los tests de integración existentes.

- [ ] **Step 5: Verificar.** `python3 -m pytest -m "not integration" -q` → green (los endpoints de orgs siguen funcionando vía el repo nuevo).

- [ ] **Step 6: Commit**

```bash
git add src/orgs/ src/api_v2.py tests/test_api_v2.py tests/test_orgs_repository.py
git commit -m "refactor(orgs): extrae OrganizationRepository de tenant_kb (desacopla el v2 del legacy)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: Eliminar `/v2/analyze` + el RAG v1 (backend)

**Files:** Modify `src/api_v2.py`, `src/multitenant_models.py`, `Dockerfile`, `tests/test_imports.py`; Delete (git rm) los módulos RAG + tests legacy + `legacy/`.

- [ ] **Step 1: Quitar `/v2/analyze` de `api_v2`.** Eliminar el endpoint `analyze_v2` (`@router.post("/analyze")` + su función), la función `get_analyzer`, el global `_analyzer`, y los imports `from src.structured_analyzer import StructuredAnalyzer` y `from src.tenant_kb import TenantKBRepository` (este último ya sin uso tras T1). Confirma con `grep -n "StructuredAnalyzer\|get_analyzer\|_analyzer\|TenantKBRepository\|analyze_v2" src/api_v2.py` → vacío.

- [ ] **Step 2: Quitar los modelos `AnalyzeV2`.** En `src/multitenant_models.py`, eliminar `AnalyzeV2Request` y `AnalyzeV2Response` (antes confirma `grep -rn "AnalyzeV2" src/ tests/` → solo en multitenant_models tras el Step 1).

- [ ] **Step 3: Borrar el RAG v1.**

```bash
git rm main.py ui.py api.py \
  src/loader.py src/vector_store.py src/model.py src/retriever.py src/prompts.py \
  src/evaluator.py src/history.py src/inspector.py src/structured_analyzer.py \
  src/scope_priority.py src/tenant_kb.py
git rm tests/test_evaluation.py tests/test_scope_priority.py
git rm -r legacy/
```

(Antes de borrar cada test, confirma que solo cubre módulos borrados. Si otro test importa algo borrado, ajústalo o bórralo según corresponda — `grep -rln "loader\|vector_store\|src.model\|retriever\|src.prompts\|evaluator\|history\|inspector\|structured_analyzer\|scope_priority\|tenant_kb" tests/`.)

- [ ] **Step 4: Dockerfile + test_imports.** En `Dockerfile`, quitar la línea `COPY api.py .`. En `tests/test_imports.py`, quitar los imports de `tenant_kb`/`structured_analyzer`/`scope_priority`; mantener `security`/`multitenant_models`/`sanitizer`; añadir `import src.orgs.repository`.

- [ ] **Step 5: Verificar.** `grep -rn "src\.\(loader\|vector_store\|model\|retriever\|prompts\|evaluator\|history\|inspector\|structured_analyzer\|scope_priority\|tenant_kb\)\|get_analyzer\|StructuredAnalyzer\|AnalyzeV2" src/ tests/` → vacío. Luego `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat!: elimina /v2/analyze y el RAG v1 (Smart Error Debugger) del backend

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Eliminar el analyze del frontend

**Files:** Delete `frontend/src/app/app/analyze/`, `frontend/src/components/analyze/`, `frontend/src/app/api/v2/analyze/`; Modify `frontend/src/lib/api/endpoints.ts`, `types.ts`, y el nav.

- [ ] **Step 1: Borrar las vistas/route.**

```bash
cd frontend
git rm -r src/app/app/analyze src/components/analyze src/app/api/v2/analyze
```

- [ ] **Step 2: Quitar del cliente.** En `src/lib/api/endpoints.ts`, eliminar `analyzeError` (y su import de `AnalyzeV2Request`/`AnalyzeV2Response`). En `src/lib/api/types.ts`, eliminar `AnalyzeV2Request`/`AnalyzeV2Response` (y cualquier tipo que quedara huérfano SOLO por el analyze — confirma con grep antes de quitar `UploadResponse`/otros). Confirma `grep -rn "analyzeError\|AnalyzeV2" src` → vacío.

- [ ] **Step 3: Quitar el enlace de navegación.** Buscar el link a `/app/analyze` (`grep -rn "analyze" src/components/layout src/app/app/layout.tsx 2>/dev/null`) y eliminar la entrada del menú/nav si existe.

- [ ] **Step 4: Verificar.** Desde `frontend/`: `npm test` → green; `tsc --noEmit` (o el typecheck) limpio; `grep -rn "analyze" src/app src/components | grep -vi "analizad\|assurance"` no debe dejar referencias colgadas al endpoint borrado.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat!: elimina la UI del analizador de errores (/v2/analyze) del frontend

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 4: README + docs + borrar el ADR

**Files:** Modify `README.md`, `.env.example`, `docs/functional/overview.md`, `doc/AUDITORIA_CONCURSO_MTP.md`, `src/__init__.py`; Delete `docs/adr/0001-pivote-a-mnemo.md`.

- [ ] **Step 1: README.** Quitar la nota "Evolución de *SmartErrorDebugger*…" y cualquier mención; si el README lista `/v2/analyze` o el "analizador de errores" como feature, quitarlo (Mnemo = Autopilot: ingesta→triaje→acción→cert→briefing).

- [ ] **Step 2: Config + docs de producto.** `.env.example`: `LANGCHAIN_PROJECT="SmartErrorDebugger"` → `LANGCHAIN_PROJECT="Mnemo"`. Quitar las menciones a SmartErrorDebugger en `docs/functional/overview.md`, `doc/AUDITORIA_CONCURSO_MTP.md`, y el docstring de `src/__init__.py` si las tiene.

- [ ] **Step 3: Borrar el ADR.** `git rm docs/adr/0001-pivote-a-mnemo.md`.

- [ ] **Step 4: Verificar.** `grep -ril "smarterrordebugger\|smart error debugger" . --include='*.md' --include='*.py' --include='*.ts' --include='*.tsx' --include='*.example' | grep -v node_modules | grep -v "docs/superpowers" | grep -v "docs/auditoria"` → vacío (lo que quede en `docs/superpowers`/`docs/auditoria` es registro de proceso, intencional). `python3 -m pytest -m "not integration" -q` → green (sanity).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: elimina las referencias a Smart Error Debugger (README/docs) + borra el ADR del pivote

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Orden importa:** T1 (extraer orgs) ANTES de T2 (borrar tenant_kb), porque T2 borra `tenant_kb` y `api_v2` ya debe usar `OrganizationRepository`.
- **`feat!`** en T2/T3 marca el cambio incompatible (se retira el endpoint `/v2/analyze` y su UI).
- **Verde en cada fase:** backend `pytest` (T1, T2, T4) + frontend `npm test`/`tsc` (T3).
- **Fuera de alcance:** Bloque C (C3/C4), God-objects, reescribir el historial de git.
