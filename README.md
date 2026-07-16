# Mnemo — QA Continuity AI

[![Backend CI](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/frontend-ci.yml)

**Mnemo** es una plataforma de continuidad operativa de QA: convierte el conocimiento disperso de un proyecto (reglas, flujos, bugs, tests, CI) en **triaje automático, actas de release verificables, planes de prueba y memoria accionable**. Pensada para consultoras de QA multi-cliente donde el conocimiento se evapora con la rotación de personal.

> **Privado por diseño:** embeddings siempre locales y LLM intercambiable — 100% on-premise con Ollama (el dato del cliente nunca sale, coste de API 0 €) o cualquier proveedor compatible OpenAI con opt-in explícito (`ALLOW_EXTERNAL_LLM`).

## El diferenciador: el acta de release firmada y verificable

Cada run de CI termina en un **certificado de aseguramiento firmado con Ed25519**: veredicto (`apto` / `apto-con-reservas` / `no-apto`), evidencia, desglose de riesgo y firma criptográfica. **Cualquiera puede verificarlo sin cuenta en Mnemo** — en la página pública `/verify`, vía `POST /v2/certificates/verify`, u offline con la clave pública (`GET /v2/certificates/pubkey`). Dos invariantes probados por tests: si la IA asistió cualquier veredicto, el acta nunca es un `apto` rotundo; y sin calibración humana suficiente, tampoco.

## Capacidades

| Capacidad | Módulo | Página |
|---|---|---|
| **Autopilot** — webhook de CI → triaje determinista R0–R6 (flaky/infra/mantenimiento/real, LLM solo en ambiguos) → acta firmada → gate en el PR | `src/ci/` · `src/triage/` · `src/certify/` | `/app/autopilot` |
| **Self-heal** — fallo de mantenimiento → parche de selector propuesto → aprobación humana → draft PR (nunca auto-merge) | `src/actions/` | panel de acciones |
| **Calibración (el foso)** — cada corrección humana entrena las métricas de confianza del motor, por cliente | `src/defects/` · tabla `triage_corrections` | `/app/calibration` |
| **Memoria del proyecto** — conocimiento de QA en 7 tipos (reglas, flujos, riesgos, glosario, lecciones, retos, patrones) + búsqueda semántica unificada con el Defect DNA | `src/knowledge/` · tabla `qa_knowledge` | `/app/knowledge` |
| **Test Plan Agent** — HU (texto / URL Jira / PDF-Word) → plan de pruebas manual o Gherkin citando la memoria, exportable a Jira-Xray | `src/testplan/` · `src/xray/` | `/app/test-plan` |
| **Onboarding Agent** — "modo persona nueva": resumen de dominio + ruta de aprendizaje + chat contra la memoria | `src/onboarding/` | `/app/onboarding` |
| **Automation Agent** — caso del plan → Playwright `.spec.ts` con el estilo del repo del cliente (tests indexados) → draft PR | `src/automation/` · `src/repo_ingest/` | botón en `/app/test-plan` |
| **Knowledge Graph + Coverage Gap** — grafo de relaciones + huecos de cobertura cruzando memoria × tests reales del repo | `src/graph/` | `/app/graph` |

**Ingesta:** webhook de CI (reporter de Playwright incluido en `packages/`) o upload de reportes con autodetección de **7 formatos** (JUnit, TestNG, Robot Framework, Allure, Playwright, Cypress, Cucumber), más issues de Jira. Idempotente extremo a extremo.

## Stack

Python 3.13 · FastAPI · Postgres + pgvector (Supabase) · Supabase JWT · LLM intercambiable (Ollama por defecto · OpenAI-compatible · Anthropic) · HuggingFace embeddings (CPU) · reporter de Playwright (TypeScript, `packages/`) · Next.js + TanStack Query + shadcn/ui · pytest/vitest.

## Documentación

| Doc | Contenido |
|---|---|
| [`docs/functional/overview.md`](docs/functional/overview.md) | Identidad, capacidades, casos de uso, personas |
| [`docs/vision/qa-continuity-ai.md`](docs/vision/qa-continuity-ai.md) | Visión, principios, arquitectura conceptual, roadmap |
| [`docs/technical/arquitectura.md`](docs/technical/arquitectura.md) | Arquitectura, capas, componentes, flujo de datos |
| [`docs/technical/modelo-datos.md`](docs/technical/modelo-datos.md) | Esquema y aislamiento multi-tenant (RLS) |
| [`docs/technical/api.md`](docs/technical/api.md) | Referencia completa de endpoints `/v2` |
| [`docs/deploy/produccion.md`](docs/deploy/produccion.md) | Desplegar frontend + backend + BD en producción |
| [`docs/demo/runbook.md`](docs/demo/runbook.md) | Operativa de la demo (datos sembrados, push en vivo, plan B) |

## Puesta en marcha

1. **Dependencias:** `pip install -r requirements.txt`.
2. **BD (Supabase):** configurar `DATABASE_URL` (Session pooler) + `SUPABASE_URL`/`SUPABASE_JWKS_URL` en `.env`; aplicar **todas** las migraciones de `db/migrations/` en orden.
3. **LLM (opcional):** `ollama pull qwen3:8b` para el modo local, o un proveedor compatible OpenAI (ver `.env.example`). Sin LLM, todo lo no-IA funciona y las funciones de IA degradan con elegancia.
4. **Backend:** `uvicorn asgi:app`.
5. **Frontend:** `cd frontend && npm install && npm run build` (proxy `/api/v2/*` → `NEXT_PUBLIC_API_BASE_URL`).
6. **Datos de demo (opcional):** `python3 scripts/docker_init.py`.

Variables por feature (todas en [`.env.example`](.env.example)): actas firmadas → `MNEMO_SIGNING_PRIVATE_KEY`/`_PUBLIC_KEY`; webhook de CI → `CI_WEBHOOK_SECRET` + `CI_SERVICE_USER_ID`; integración Jira/Xray → `MNEMO_SECRET_KEY`; gate y draft PR → `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY`.

## Despliegue

- **Frontend (Next.js) → Vercel.** Root Directory = `frontend`; Node 22.x (ver `frontend/.nvmrc`). Variables: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- **Backend (FastAPI) → Render** (blueprint `render.yaml`) **u on-premise** con Ollama para data-residency estricta. Guía completa: [`docs/deploy/produccion.md`](docs/deploy/produccion.md).

## Tests

```bash
python3 -m pytest -m "not integration"   # unitarios (sin BD/LLM) — lo que corre el CI
python3 -m pytest -m integration         # integración — OJO: corre contra la BD de DATABASE_URL
cd frontend && npm run check:ci          # lint + vitest + build (lo que corre el CI)
```
