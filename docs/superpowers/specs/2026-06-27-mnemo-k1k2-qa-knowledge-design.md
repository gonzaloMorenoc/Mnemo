# QA Continuity AI · Fase 1a: Memoria del proyecto (capturar + buscar/preguntar) — diseño

**Fecha:** 2026-06-27 · **Parte de:** [QA Continuity AI](../../vision/qa-continuity-ai.md), Fase 1a (cimiento) · **Base:** `main` 53bd9d9 · **Backend:** Python/FastAPI/Postgres+pgvector · **Frontend:** Next.js/TS.

## Encuadre

Primer sub-proyecto de QA Continuity AI: la **memoria del proyecto**. Captura el conocimiento de QA (reglas de negocio, flujos, riesgos, glosario, lecciones, retos, patrones) y lo hace **consumible** (búsqueda + asistente), **unificado con el Defect DNA** existente. Es el cimiento sobre el que se apoyan el **Test Plan Agent** (Fase 1b) y el resto del roadmap. El Autopilot (ingesta→triaje→acción→cert) queda como una **fuente** que alimentará esta memoria (Fase 3).

No se parte de cero: se extiende la maquinaria semántica que ya existe — `LocalEmbedder` (`src/defects/embedder.py`), `search_families_semantic` (`repository.py:928`), `nl_query.answer_question` (`src/ai/nl_query.py`), pgvector + RLS.

## Decisiones (confirmadas)

- **Entidad `qa_knowledge`** independiente + vinculable opcional a una familia de defecto / run; con vocabulario alineado al modelo de QA Continuity (`kind` = regla/flujo/riesgo/glosario/lección/reto/patrón) + `domain` (área funcional).
- **Consumo unificado**: la búsqueda y el asistente razonan a la vez sobre `qa_knowledge` **y** las familias de defecto.
- **Captura manual** en esta fase (la auto-extracción desde los runs es la Fase 3); pero el esquema ya prevé `source` + `confidence` (principio "citar fuentes + confianza") para no rehacer la tabla.
- **El LLM local asiste, no decide ni firma** — el asistente cita las fuentes; degrada sin LLM a un listado. Coherente con "determinismo donde firmo, IA donde multiplico", sin el riesgo de "perfección" del certificado.

## Componentes

### 1. Tabla `qa_knowledge` (migración SQL nueva)
```
id uuid pk · org_id uuid not null → organizations
kind text check in ('regla_negocio','flujo','riesgo','glosario','leccion','reto','patron')
title text not null · challenge text · approach text · outcome text
domain text                          -- área funcional (p.ej. "facturacion") para "¿qué sabe el proyecto sobre X?"
tags text[] default '{}' · project text
source text not null default 'manual'           -- futuro: 'jira'|'confluence'|'auto'... (Fase 3)
confidence text not null default 'confirmado' check in ('confirmado','inferido')
defect_family_id uuid null → defect_families(id) on delete set null   -- vínculo opcional
run_id uuid null → test_runs(id) on delete set null                   -- vínculo opcional
created_by uuid not null · created_at timestamptz default now() · embedding vector(384)
```
+ índice ivfflat sobre `embedding` (vector_cosine_ops) + índices sobre `org_id` y `domain`. **RLS: enable + FORCE + policy `is_org_member`** (invariante del proyecto para toda tabla `public`). Aplicar a la **BD de prod vía psql** (DATABASE_URL=prod) + verificar `relrowsecurity`/`relforcerowsecurity`.

### 2. `QaKnowledgeRepository` (`src/knowledge/repository.py`, módulo nuevo)
- `create_item(*, user_id, org_id, kind, title, challenge, approach, outcome, domain=None, tags, project, source="manual", confidence="confirmado", defect_family_id=None, run_id=None) -> dict` — membership-gated; vectoriza `title + "\n" + challenge + "\n" + approach` con `LocalEmbedder`; inserta con el embedding.
- `list_items(*, user_id, org_id, kind=None, domain=None) -> list` — membership-gated, orden por `created_at desc`.
- `get_item(*, user_id, org_id, item_id) -> dict|None` — membership-gated.
- `search_semantic(*, user_id, org_id, query_embedding, k=8) -> list` — coseno sobre `embedding`, membership-gated (mismo patrón exacto que `search_families_semantic`).
- Reusa `_connect`/`_set_claims` (extraer una base común si conviene; ver auditoría DRY).

### 3. Búsqueda unificada + asistente (`src/knowledge/service.py` + extender `src/ai/nl_query.py`)
- `KnowledgeService.search_unified(*, user_id, org_id, query, k)`: vectoriza `query` con `LocalEmbedder`; llama `QaKnowledgeRepository.search_semantic` **y** `AssuranceRepository.search_families_semantic`; devuelve una lista combinada de fuentes `{id, type: "knowledge"|"defect", title, content, score}`.
- `nl_query`: añadir `answer_over_sources(*, question, sources, provider=None)` que acepta fuentes mixtas (`{id, content, type}`) y responde citando los `id`; degrada sin LLM al listado. Refactorizar `answer_question` (Defect DNA) para delegar en ella (DRY) manteniendo su comportamiento.
- `KnowledgeService.ask(*, user_id, org_id, question)`: `search_unified` → `answer_over_sources` → `{answer, citations:[{id,type}]}`.

### 4. Endpoints (`src/api_v2.py`)
- `POST /v2/knowledge` (crear ítem) — `Depends(get_current_user)`, member del org (crear conocimiento es colaborativo/aditivo; NO es etiquetar calibración).
- `GET /v2/knowledge?org_id=&kind=&domain=` (listar) · `GET /v2/knowledge/{id}` (detalle).
- `POST /v2/knowledge/search` (`{org_id, query, k}` → fuentes unificadas).
- `POST /v2/knowledge/ask` (`{org_id, question}` → `{answer, citations}`).
- Todos membership-gated; degradan con elegancia (LLM caído → search sin asistente).

### 5. Frontend (`frontend/src/app/app/knowledge/` + cliente)
- Página **Conocimiento**: (a) **capturar** (form: kind, title, challenge, approach, outcome, domain, tags, project); (b) **buscar/preguntar** (input → resultados unificados citados + respuesta del asistente, marcando cada fuente como conocimiento o defecto, con su `confidence`). Usa la org activa (`useActiveOrg`, de C4).
- Cliente: `createKnowledge`, `listKnowledge`, `searchKnowledge`, `askKnowledge` en `lib/api/endpoints.ts` + tipos. Nav: entrada "Conocimiento" en el sidebar.
- (Nota: el viejo `/app/knowledge` del KB legacy se borró en #40; este es un concepto nuevo — conocimiento de QA, no upload de docs.)

## Garantías

- **Multi-tenant:** `qa_knowledge` con RLS+force+policy; todas las queries membership-gated (el pooler bypassa RLS → check app-layer, como el resto). La búsqueda unificada nunca cruza orgs.
- **IA asiste, no decide:** el asistente cita fuentes (con `confidence`) y degrada sin LLM; no firma ni altera veredictos. El conocimiento es informativo.
- **Reusa, no duplica:** embedder, patrón de búsqueda vectorial y `nl_query` se comparten con el Defect DNA.
- **El Autopilot/cert intactos:** este sub-PR no toca el triaje/certificado/gate.

## Testing

- **Backend:** `QaKnowledgeRepository` (create vectoriza + list/get membership-gated, filtro por kind/domain); `search_unified` combina knowledge + families; `answer_over_sources` cita y degrada sin LLM; los endpoints (crear/listar/search/ask, auth + 401 sin auth + aislamiento). Integración (BD prod, cleanup): crear un ítem → buscarlo semánticamente. `python3 -m pytest -m "not integration"` + integración.
- **Frontend (vitest):** el form de captura llama `createKnowledge`; la búsqueda/chat renderiza resultados unificados citados; degrada si `ask` falla. `npm test` + `tsc`.

## Fuera de alcance (siguientes pasos de QA Continuity AI)

- **Fase 1b:** Test Plan Agent (HU → plan con riesgos/sistemas/gaps, citando esta memoria).
- **Fase 2:** Knowledge Graph (relaciones) + Coverage Gap Detector + "¿qué sabe el proyecto?".
- **Fase 3:** ingesta multi-fuente (Jira historias/criterios, Confluence, Git, OpenAPI) → poblar `source`/`confidence` automáticamente.
- **Fase 4:** Automation Agent (Gherkin→Playwright→PR) + Onboarding Path. Rediseño del Autopilot/certificado.
