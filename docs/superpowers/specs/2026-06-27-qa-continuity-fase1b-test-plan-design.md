# QA Continuity AI · Fase 1b: Test Plan Agent — diseño

**Fecha:** 2026-06-27 · **Parte de:** [QA Continuity AI](../../vision/qa-continuity-ai.md), Fase 1b · **Base:** sobre la Fase 1a (memoria, PR #43). · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

Dada una **historia de usuario** (de Jira por URL, de un PDF/Word, o texto libre) → generar un **plan de pruebas** estructurado que **cita la memoria del proyecto** (Fase 1a + Defect DNA), con los casos en formato **manual** o **Gherkin**. El plan es **efímero en Mnemo** (no se guarda en BD); se **edita** en el cliente, se **re-genera**, se **exporta a Markdown** y se **importa a Jira vía la API de Xray**. El LLM **propone**; el humano edita y aprueba. Página propia `/app/test-plan`.

## Decisiones (confirmadas)

- **Todo en un PR** (generador + ingesta multi-fuente + export Xray + página).
- **Entrada multi-fuente:** URL de issue de Jira · subir PDF/Word · texto libre.
- **Selector manual/Gherkin:** cambia **solo el formato de los casos** (manual = pasos + resultado esperado; Gherkin = Feature/Scenario Given-When-Then); el resto del plan (resumen, sistemas, riesgos, datos, gaps, preguntas) es igual.
- **Plan efímero en Mnemo**; su persistencia real es exportar (Markdown) o importar a Jira/Xray. Editar = estado en cliente; re-generar = re-llamar al agente.
- **LLM asiste/propone + degrada sin LLM** (devuelve las fuentes recuperadas + aviso; nunca firma).

## Componentes

### 1. Test Plan Agent (`src/knowledge/test_plan.py`)
`generate_test_plan(*, knowledge_service, user_id, org_id, hu_text, case_format) -> dict`. Patrón de `src/ai/briefing.py`:
- `KnowledgeService.search_unified(user_id, org_id, query=hu_text, k=8)` recupera la memoria relevante (conocimiento + familias de defecto).
- Construye el contexto citable `[{id, content}]` de esas fuentes.
- `_TEST_PLAN_SCHEMA` = `{summary, systems:(), risks:(), preconditions:(), test_data:(), cases:(), gaps:(), open_questions:(), citations:()}`; cada `case` = `{title, level (api|e2e|data|manual), priority (alta|media|baja|critica), automatable (bool), steps (manual) | gherkin (str)}`.
- `prompt` instruye el formato de los casos según `case_format` ∈ (`manual`,`gherkin`) y pide citar en `citations` los `id` de las fuentes; `generate_structured(..., on_failure="none")` → si None, degrada a `{... fuentes recuperadas, aviso "LLM no disponible", citations}`.

### 2. Ingesta de la HU (`src/testplan/ingest.py`)
`resolve_hu(*, text=None, jira_url=None, file=None, jira_client=None) -> str` (normaliza a `hu_text`):
- **Jira:** `JiraApiClient.fetch_issue(key)` (añadir a `src/jira/client.py`; parsear la key de la URL, p.ej. `.../browse/DIA-1234`) → `summary + description + acceptance criteria` (los campos que exponga). Reusa la config Jira cifrada por org (`src/jira/integrations_repository.py`).
- **Fichero:** PDF → `pypdf` (ya en requirements); Word `.docx` → `python-docx` (nueva dependencia) → texto. Cota de tamaño + sanitiza.
- **Texto libre:** tal cual.

### 3. Export a Jira/Xray (`src/xray/`)
- **Config Xray cifrada por org** (patrón `src/jira/integrations_repository.py` + la tabla `org_integrations`, migración 013): credenciales (Cloud: client_id/secret → token bearer; Server/DC: usuario/token). 
- `XrayClient.import_plan(*, plan, case_format)`: manual → crea Test issues con steps; Gherkin → importa el/los `.feature` (endpoint de import de Cucumber de Xray). Devuelve los keys creados. Error claro si no hay config Xray (503/aviso, no rompe).
- (La API exacta — Xray Cloud GraphQL vs Server REST — se fija en el plan según la instancia del usuario; el cliente es configurable.)

### 4. Endpoints (`src/api_v2.py` + modelos)
- `POST /v2/test-plan/generate` (`{hu_text? , jira_url?, case_format}` o `multipart` con `file`) → ingesta (`resolve_hu`) + `generate_test_plan` → `{plan, citations}`. (Re-generar = volver a llamar.)
- `POST /v2/test-plan/export/markdown` (`{plan}`) → `text/markdown` (o el cliente lo arma).
- `POST /v2/test-plan/export/xray` (`{plan, case_format}`) → importa a Xray, devuelve los keys. 503 si no hay config Xray.
- Todos `Depends(get_current_user)`, membership-gated, con `org_id`.

### 5. Frontend `/app/test-plan` (+ cliente + nav)
- **Entrada:** tres modos (Jira URL · subir PDF/Word · textarea) + selector **manual/Gherkin** + botón **Generar**. Usa `useActiveOrg`.
- **Plan:** render estructurado (resumen/sistemas/riesgos/datos/casos/gaps/preguntas) con las **citas** a la memoria; campos **editables en cliente**; botones **Re-generar**, **Exportar Markdown**, **Importar a Jira (Xray)**.
- Degrada: LLM caído → muestra las fuentes + aviso; Xray sin config → toast "configura Xray".
- Cliente: `generateTestPlan`, `exportTestPlanMarkdown`, `exportTestPlanXray` + tipos. Nav: entrada "Plan de pruebas".

## Garantías

- **IA propone, humano aprueba:** el plan es editable y nunca se importa/exporta sin acción del usuario; el LLM no firma.
- **Multi-tenant:** la memoria recuperada y la config Xray/Jira son por org (membership-gated, config cifrada).
- **Degradación:** sin LLM → fuentes + aviso; sin config Xray → 503/aviso; ficheros corruptos → error claro.
- **Reusa:** `search_unified` (1a), `briefing` pattern, `generate_structured`, `src/jira` (cliente + config cifrada), `pypdf`.

## Testing

- **Backend:** `generate_test_plan` (genera con `generate_structured` mockeado → plan con casos en el formato pedido + citas; degrada sin LLM); `resolve_hu` (jira mock / PDF / docx / texto → hu_text); `XrayClient.import_plan` (mock de la API → keys; sin config → error); endpoints (generate/export, auth + 401 + membership + 503 sin Xray). `python3 -m pytest`.
- **Frontend (vitest):** la página genera (mock `generateTestPlan`), edita un campo, re-genera, exporta MD, e importa Xray (mock); degrada si generate/Xray fallan. `npm test` + `tsc`.

## Riesgos / notas

- **Xray** necesita credenciales/instancia reales para la prueba e2e; en CI se mockea. La forma exacta de la API (Cloud GraphQL vs Server REST) se concreta en el plan.
- **Tamaño:** es el sub-PR más grande de QA Continuity hasta ahora (agente + 3 ingestas + Xray + página). El plan lo descompone en tareas; el orden sugerido: agente core → ingesta → Xray → frontend.

## Fuera de alcance

- **Fase 2:** Knowledge Graph + Coverage Gap Detector (los gaps de 1b son vía LLM).
- **Fase 4:** Automation Agent (generar el código Playwright de los casos) — 1b llega hasta el plan/Gherkin + import a Xray, no genera el código de test.
