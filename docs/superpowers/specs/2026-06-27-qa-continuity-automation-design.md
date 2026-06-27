# QA Continuity AI · Automation Agent (Fase 4) — diseño

**Fecha:** 2026-06-27 · **Parte de:** [QA Continuity AI](../../vision/qa-continuity-ai.md), 4ª y última capacidad · **Base:** `main` 3647ee6 (1a+1b+onboarding) · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

Cerrar el ciclo **HU → plan → código → PR**: de un **caso del plan de pruebas** (1b) en Gherkin/pasos → generar el **código Playwright** (`.spec.ts`) **al estilo del repo** → abrir un **draft PR** (opcional). **IA propone, el humano revisa/ejecuta/aprueba; nunca auto-merge** — un draft revisable, no un veredicto firmado (mitiga el problema de "perfección" del LLM local).

## Decisiones (confirmadas)

- **Estilo del repo:** few-shot con un **sample pegado/subido** por el cliente (1-2 tests existentes); sin sample → convenciones Playwright estándar.
- **Entrada:** **botón "Generar test Playwright" por caso en `/app/test-plan`** (flujo plan→código sin copiar).
- **Salida:** genera el código (mostrar/**descargar** siempre) + **draft PR opcional** si hay config GitHub por org; degrada a solo-código sin config.
- **MVP no ejecuta** el test (Playwright necesita navegador + la app bajo test); genera + PR; el humano lo corre. Todo en **un PR**.

## Componentes

### 1. Agente (`src/automation/agent.py`, patrón `ai_repair`/`testplan`)
`generate_playwright_test(*, case, style_sample=None, provider=None) -> dict`:
- `case` = el caso del plan (1b): `{title, gherkin?, steps?, level, priority, ...}`.
- Prompt: genera un test Playwright completo (`.spec.ts`) para el caso; **si `style_sample`**, imítalo (few-shot: selectores, page objects, fixtures); si no, convenciones estándar. Marca el contexto como datos no confiables.
- `_TEST_SCHEMA = {code, filename, notes}`; `generate_structured(..., on_failure="none")` → si None, **degrada** a una plantilla básica (`test('<title>', ...)` con `// TODO` + los pasos como comentarios) + `notes: "LLM no disponible"`. Nunca lanza ni firma. Type-guards.

### 2. GitHub: crear fichero nuevo + PR (`src/ci/github_app.py`)
`open_draft_pr` actual hace **replace** (`old_str`→`new_str`) en un fichero existente (self-heal) — **no sirve** para un test nuevo. Se añade:
`GitHubCodeHost.open_pr_with_new_file(*, title, body, file_path, content, marker="") -> Optional[str]`:
- Reusa los helpers privados: `_default_branch`, `_ref_sha`, `_create_ref(branch, base_sha)`, `_put_file(file_path, content, file_sha=None, branch, message)` (con `file_sha=None` → **crea**), `_create_pr`. Rama `mnemo/automation/<marker o slug>`.
- Si el fichero ya existe (`_get_file` devuelve sha) → actualiza ese contenido (o sufija el nombre); idempotente vía `_find_pr_by_head` como `open_draft_pr`.

### 3. Endpoints (`src/api_v2.py` + modelos)
- `POST /v2/automation/generate` (`{org_id, case: dict, style_sample?: str}` → `{code, filename, notes}`): `generate_playwright_test(...)`.
- `POST /v2/automation/pr` (`{org_id, code, filename, title?, case_title?}` → `{pr_url}`): reusa `_github_codehost_factory(org_id, user_id)` (config GitHub por org cifrada, ya existe) → `open_pr_with_new_file`. **503** si no hay config GitHub; 502 en error de API.
- Ambos `Depends(get_current_user)`, membership-gated. Modelos `AutomationGenerateRequest`, `AutomationPrRequest`.

### 4. Frontend (`/app/test-plan` + cliente)
- En la página de plan (1b), en cada **caso** renderizado: botón **"Generar test Playwright"** → `generatePlaywrightTest({org_id, case, style_sample})` → muestra el código (sección/modal con resaltado) + **Descargar** (`.spec.ts`) + **"Abrir draft PR"** (`openAutomationPr` → toast con la URL; sin config GitHub → toast "configura GitHub"). Un campo opcional **"ejemplo de estilo"** (textarea, a nivel de plan, se reusa para todos los casos).
- Cliente: `generatePlaywrightTest`, `openAutomationPr` + tipo `GeneratedTest` (`{code, filename, notes}`).

## Garantías

- **IA propone, humano aprueba:** el código es un draft; el PR es *draft* y nunca se auto-mergea; el humano lo ejecuta y revisa.
- **Degradación:** sin LLM → plantilla básica + aviso; sin config GitHub → 503/solo-código; caso vacío → 400.
- **Multi-tenant:** generate es membership-gated; el PR usa la config GitHub por org (cifrada, la misma de self-heal/F3c).
- **Reusa:** `generate_structured`, el patrón `ai_repair`/`testplan`, `GitHubCodeHost` + `_github_codehost_factory`, los casos Gherkin de 1b, la página `/app/test-plan`.
- **Sin migración** (config GitHub ya en `org_integrations`).

## Testing

- **Backend:** `generate_playwright_test` (mock `generate_structured` → code con el caso; `style_sample` entra en el prompt; degrada sin LLM a plantilla); `open_pr_with_new_file` (mock HTTP → pr_url; fichero nuevo vs existente; idempotencia); endpoints (auth + 401 + membership + 200 + **503 sin GitHub**). `python3 -m pytest -m "not integration"`.
- **Frontend (vitest):** un caso del plan → "Generar test Playwright" llama `generatePlaywrightTest` y muestra el código; "Abrir draft PR" llama `openAutomationPr` (mock) → toast; sin config → toast.error; degrada si generate falla. `npm test` + `tsc`.

## Fuera de alcance

- **Ejecutar/validar** el test en un navegador (necesita la app bajo test) — el humano lo corre.
- **Fase 2:** Knowledge Graph + Coverage Gap.
- **Leer el repo** automáticamente para el estilo (eso es Fase 3 / ingesta) — aquí el estilo es un sample que pega el cliente.
