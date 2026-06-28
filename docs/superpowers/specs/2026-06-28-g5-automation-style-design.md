# QA Continuity AI · G5: Automation al estilo del repo — diseño

**Fecha:** 2026-06-28 · **Parte de:** [Roadmap de cierre de gaps](../../vision/qa-continuity-gaps-roadmap.md), fase **G5** · **Base:** `main` 572503a (G1 + G2) · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

Cerrar el círculo **"detecto el hueco → genero el test que falta, al estilo del repo → PR"**. Dos mejoras sobre el Automation Agent (#46):
1. **Few-shot real:** el agente genera Playwright usando los **tests reales del repo** (`test_assets`, G1) como ejemplos de estilo, en vez del `style_sample` que hoy se pega a mano.
2. **Generar desde un gap:** desde un `regla_sin_test` (G2) en `/app/graph`, un botón **"Generar test"** produce el test que falta para esa regla.

## Decisiones (confirmadas)

- **Alcance:** few-shot real + generar-desde-gap. (API/contract/SQL tests y ejecutar el test = iteración posterior.)
- **Estilo en cascada:** `style_sample` manual (si lo pegas) → si no, los `test_assets` más similares al caso → si no hay tests indexados, convenciones estándar.
- **`generate` pasa a requerir `org_id` + membership:** hoy `/v2/automation/generate` no usa `org_id` (no tocaba datos del org); G5 recupera `test_assets` **del org** para el few-shot, así que ahora necesita `org_id`; el retrieval es membership-gated (no-miembro → sin few-shot, cae a estándar; sin fuga). El agente sigue **puro** (recibe los ejemplos como texto).
- IA propone (draft PR, nunca auto-merge); degrada (sin tests → estándar; sin LLM → plantilla); multitenant; **sin migración**.

## Componentes

### 1. Recuperación del few-shot (`src/automation/` o el endpoint)
Una función `retrieve_style_examples(*, user_id, org_id, case_text, asset_repo, embedder, k=3) -> str | None`: embed(`case_text`) → `TestAssetRepository.search_semantic(user_id, org_id, query_embedding, k)` → concatena el `content` de los top-k (con separadores `// --- ejemplo: <path> ---`) hasta una cota (~6 000 chars). Devuelve `None` si no hay tests. Membership-gated (vía `search_semantic`).

### 2. Endpoint `POST /v2/automation/generate` (modificar)
- `AutomationGenerateRequest`: añadir `org_id: str` (junto a `case`, `style_sample?`).
- Cascada: `examples = req.style_sample or retrieve_style_examples(user_id, org_id, _case_text(case), …)`; `generate_playwright_test(case=req.case, style_sample=examples)`. (El agente ya trata `style_sample` como ejemplos de estilo; no cambia.)
- El retrieval es membership-gated; el endpoint no necesita un 403 propio (no-miembro → sin few-shot). `case` vacío → 400 (ya existe).

### 3. "Generar desde un gap" (frontend, orquesta endpoints existentes)
El gap `regla_sin_test` lleva `affected=[qa_knowledge id]`. Al pulsar **"Generar test"**: `getKnowledgeItem(id)` (cliente nuevo sobre `GET /v2/knowledge/{id}`, que ya existe en backend) → construye el caso `{title: item.title, steps: [item.challenge, item.approach, item.outcome].filter(Boolean)}` → `generatePlaywrightTest({org_id, case})` → muestra el `code` + `notes` + **"Abrir draft PR"** (`openAutomationPr`, ya existe). Degrada (error → toast).

### 4. Frontend
- `frontend/src/app/app/test-plan/page.tsx`: el botón "Generar test Playwright" ahora pasa `org_id` (para el few-shot auto); el campo de "estilo" manual se mantiene como override opcional.
- `frontend/src/app/app/graph/page.tsx`: en cada gap `regla_sin_test`, un botón **"Generar test"** + una sección que muestra el código generado (mono `<pre>`) + Descargar + "Abrir draft PR" (reusa el patrón de test-plan).
- Cliente: `generatePlaywrightTest` añade `org_id` al body; nuevo `getKnowledgeItem(token, {org_id, id})` → `GET /api/v2/knowledge/{id}?org_id=…` (confirmar la firma real del endpoint de 1a).

## Garantías

- **Reusa:** `generate_playwright_test`/`open_pr_with_new_file` (#46), `TestAssetRepository.search_semantic` (G1), el gap `regla_sin_test` (G2), `GET /v2/knowledge/{id}` (1a), el patrón de UI de código+PR de test-plan.
- **IA propone, no firma:** draft PR; el humano revisa. **Degrada:** sin tests → estándar; sin LLM → plantilla; sin GitHub → 503 en el PR.
- **Multi-tenant:** el few-shot retrieval es membership-gated (`search_semantic`); `org_id` requerido en `generate`.
- **Sin migración / sin tabla** (reusa `test_assets`/`qa_knowledge`/`automation`).

## Testing

- **Backend:** `retrieve_style_examples` (asset_repo fake → concatena top-k; sin tests → None; membership → None para no-miembro); el endpoint `generate` (cascada: con `style_sample` manual lo usa; sin él, usa los test_assets recuperados; sin tests, None → estándar; el agente recibe los ejemplos). `python3 -m pytest -m "not integration"`.
- **Frontend (vitest):** el botón de test-plan pasa `org_id`; en el panel de gaps, "Generar test" en un `regla_sin_test` → `getKnowledgeItem` + `generatePlaywrightTest` → muestra el código; "Abrir draft PR" → `openAutomationPr`; degrada. `npm run lint:ci` + `test` + `tsc` + `build`.

## Verificación local = CI (obligatoria; recordar `npm --prefix frontend ci` si node_modules se corrompe)
Frontend `lint:ci`+`test`+`build`; backend pytest **sin `.env`**.

## Fuera de alcance
- API/contract/SQL tests; ejecutar/compilar el test antes del PR.
- Reranking del few-shot por framework; calibrar el k.
- Persistir el test generado en Mnemo (sigue siendo efímero → PR).
