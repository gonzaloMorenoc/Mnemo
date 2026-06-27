# QA Continuity AI · Onboarding Agent — diseño

**Fecha:** 2026-06-27 · **Parte de:** [QA Continuity AI](../../vision/qa-continuity-ai.md), 3ª capacidad (onboarding) · **Base:** `main` 05a11e7 (1a+1b mergeadas) · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

La promesa central de QA Continuity AI: **que una persona nueva entienda el proyecto y sea productiva** usando la memoria acumulada (Fase 1a + Defect DNA). Tres piezas, reunidas en una página "modo persona nueva":
- **¿Qué sabe el proyecto sobre X?** — resumen de un dominio.
- **Ruta de aprendizaje** — plan de incorporación por módulo.
- **Chat** — el `ask` de la Fase 1a (preguntas libres con citas), reusado.

## Decisiones (confirmadas)

- **Dos agentes** (`summarize_domain` + `learning_path`) + el chat (`ask`) reusado, todo en `/app/onboarding` ("modo persona nueva" = orquestación, no un flujo nuevo).
- **Recuperación por búsqueda semántica** (`KnowledgeService.search_unified`) sobre el tema/dominio (conocimiento + Defect DNA).
- **LLM propone, cita fuentes y degrada sin LLM** (patrón `briefing`/`test_plan`); nunca firma.

## Componentes

### 1. Agentes (`src/onboarding/agent.py`, patrón de `src/testplan/agent.py`)
- `summarize_domain(*, knowledge_service, user_id, org_id, topic, provider=None) -> dict`: `search_unified(query=topic, k=8)` → contexto citable `[{id,content}]` → `generate_structured(_SUMMARY_SCHEMA, on_failure="none")` → degrada a `_fallback` (fuentes citadas + aviso). `_SUMMARY_SCHEMA` = `{rules, systems, existing_tests, historical_bugs, risks, citations}` (listas + citations).
- `learning_path(*, knowledge_service, user_id, org_id, topic, provider=None) -> dict`: igual patrón; `_PATH_SCHEMA` = `{days, citations}` donde `days` = lista de `{day:int, items:[str]}` (Día 1 leer/flujo feliz; Día 2 negativos+bugs; Día 3 automatizar uno simple). Degrada a `_fallback`.
- `src/onboarding/__init__.py` vacío.

### 2. Endpoints (`src/api_v2.py` + modelos)
- `POST /v2/onboarding/domain-summary` (`{org_id, topic}` → `{summary, citations}`).
- `POST /v2/onboarding/learning-path` (`{org_id, topic}` → `{path, citations}`).
- El chat reusa el `POST /v2/knowledge/ask` existente (1a) — no se duplica.
- Ambos `Depends(get_current_user)`, membership-gated; construyen `KnowledgeService(get_knowledge_repo(), get_assurance_repo())`. Modelos `OnboardingRequest` (`org_id`, `topic` con cota).

### 3. Frontend (`frontend/src/app/app/onboarding/page.tsx` + cliente + nav)
- Página **Onboarding** ("modo persona nueva"): un input de **tema/dominio** + acciones que llaman `domainSummary` y `learningPath`; render del resumen (reglas/sistemas/tests/bugs/riesgos + citas) y de la ruta (días→items + citas); más un **chat** embebido que reusa `askKnowledge` (de 1a) para preguntas libres citadas. `useActiveOrg`. Degrada: si un agente falla → toast, no rompe.
- Cliente: `domainSummary(token, body)`, `learningPath(token, body)` + tipos `DomainSummary`/`LearningPath`. Nav: entrada "Onboarding".

## Garantías

- **IA asiste, no firma:** resúmenes y rutas son orientativos, citados, y degradan sin LLM (nunca lanzan). No tocan veredictos/certificados.
- **Multi-tenant:** la recuperación es membership-gated (vía `search_unified` de 1a) y los endpoints exigen membership.
- **Reusa, no duplica:** `search_unified`, el patrón de agente, el `ask`/`answer_over_sources` y la página patrón de 1a/1b.
- **Sin migración** (no hay tabla nueva; lee la memoria existente).

## Testing

- **Backend:** `summarize_domain`/`learning_path` (con `search_unified` fake + `generate_structured` patcheado → estructura + citas; degradan sin LLM a fallback con fuentes); endpoints (auth + 401 + membership + 200 con estructura). `python3 -m pytest -m "not integration"`.
- **Frontend (vitest):** la página llama `domainSummary`/`learningPath` y renderiza resumen/ruta + citas; el chat reusa `askKnowledge`; degrada si un agente falla. `npm test` + `tsc`.

## Fuera de alcance

- **Fase 2:** Knowledge Graph + Coverage Gap Detector.
- **Fase 4:** Automation Agent (generar el código Playwright). El "Día 3: automatizar un escenario simple" de la ruta es una recomendación textual, no genera código aquí.
