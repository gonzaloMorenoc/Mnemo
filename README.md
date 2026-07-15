# Mnemo — QA Continuity AI

**Mnemo** es una plataforma **privada y on-premise** de continuidad operativa de QA: convierte el conocimiento disperso de un proyecto (reglas, flujos, bugs, tests, CI) en **planes de prueba, automatización y memoria accionable**. Pensada para consultoras de QA multi-cliente donde el conocimiento se evapora con la rotación de personal.

> LLM y embeddings 100% locales (Ollama + HuggingFace). El dato del cliente nunca sale. Coste de API = 0 €.

## Cinco capacidades (todas en producción)

| Capacidad | Módulo | Página |
|---|---|---|
| **Memoria del proyecto** — captura conocimiento de QA (reglas, flujos, riesgos, lecciones) + búsqueda semántica unificada con el Defect DNA (`search_unified`) | `src/knowledge/` · tabla `qa_knowledge` | `/app/knowledge` |
| **Test Plan Agent** — HU (URL Jira / PDF-Word / texto) → plan de pruebas manual o Gherkin citando la memoria, exportar Markdown o importar a Jira-Xray | `src/testplan/` · `src/xray/` | `/app/test-plan` |
| **Onboarding Agent** — "modo persona nueva": ¿qué sabe el proyecto sobre X? + ruta de aprendizaje + chat | `src/onboarding/` | `/app/onboarding` |
| **Automation Agent** — caso del plan → código Playwright `.spec.ts` → draft PR (GitHub App, nunca auto-merge) | `src/automation/` · `src/ci/github_app.py` | botón en `/app/test-plan` |
| **Knowledge Graph + Coverage Gap** — grafo de relaciones derivado + detector de huecos de cobertura | `src/graph/` | `/app/graph` |

El **Autopilot** (ingesta CI → triaje → certificado → self-heal) actúa como fuente que alimenta la memoria; no es el centro del producto.

## Stack

Python 3.13 · FastAPI · Postgres + pgvector (Supabase) · Supabase JWT · Ollama (`qwen3:8b`) · HuggingFace embeddings · reporter de Playwright (TypeScript, `packages/`) · Next.js + TanStack Query + shadcn/ui · pytest/vitest.

## Documentación

| Doc | Contenido |
|---|---|
| [`docs/functional/overview.md`](docs/functional/overview.md) | Identidad, capacidades, casos de uso, personas |
| [`docs/vision/qa-continuity-ai.md`](docs/vision/qa-continuity-ai.md) | Visión, principios, arquitectura conceptual, roadmap |
| [`docs/technical/arquitectura.md`](docs/technical/arquitectura.md) | Arquitectura, capas, componentes, flujo de datos |
| [`docs/technical/modelo-datos.md`](docs/technical/modelo-datos.md) | Esquema y aislamiento multi-tenant (RLS) |
| [`docs/technical/api.md`](docs/technical/api.md) | Referencia completa de endpoints `/v2` |

## Puesta en marcha

1. **Modelo local:** `ollama pull qwen3:8b`.
2. **Dependencias:** `pip install -r requirements.txt`.
3. **BD (Supabase):** configurar `DATABASE_URL` (Session pooler) + `SUPABASE_URL`/`SUPABASE_JWKS_URL` en `.env`; aplicar **todas** las migraciones en orden (`db/migrations/001_*.sql` … `019_*.sql`).
4. **Backend:** `uvicorn asgi:app`.
5. **Frontend:** `cd frontend && npm install && npm run build` (proxy `/api/v2/*` → `NEXT_PUBLIC_API_BASE_URL`).
6. **Datos de demo (opcional):** `python3 scripts/docker_init.py`.

> Referencia completa de endpoints en [`docs/technical/api.md`](docs/technical/api.md).

## Despliegue

- **Frontend (Next.js) → Vercel.** Root Directory = `frontend`; Node 22.x (ver `frontend/.nvmrc`). Variables: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- **Backend (FastAPI + LLM + BD) → on-premise.** Necesita Ollama, embeddings locales y Postgres; no va en Vercel.

## Tests

```bash
python3 -m pytest -m "not integration"   # unitarios (sin BD/LLM)
python3 -m pytest -m integration         # integración (requiere DATABASE_URL)
cd frontend && npm test                  # vitest
```
