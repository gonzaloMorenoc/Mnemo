# Mnemo — continuidad del conocimiento de QA

[![Backend CI](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/frontend-ci.yml)

En una consultora de QA, los consultores rotan. Cuando la persona que lleva un proyecto se
va, con ella se van cosas que no están escritas en ningún sitio: cómo se levanta el
entorno, con qué datos se prueba, a quién se pregunta cuando el sandbox se cae, y **por
qué** un test que parece inestable en realidad no lo es.

**Mnemo es la memoria del proyecto que se queda.** Se alimenta del trabajo de cada día —
cada run del CI se ingiere, se clasifica y se firma—, guarda lo que el equipo explica al
etiquetar un fallo o documentar el oficio del proyecto, y lo devuelve a quien llega, con
la fuente citada. Pensada para consultoras de QA con varios clientes.

## Cómo funciona, en tres piezas

1. **El lazo del CI** — cada run entra por webhook o subida de informe → el motor de
   triaje determinista (reglas R0–R6, el LLM solo desempata los ambiguos) clasifica cada
   fallo como real, inestable, de entorno o de mantenimiento y dice qué regla aplicó → el
   run termina en un **acta firmada (Ed25519)** verificable por cualquiera.
2. **La memoria** — familias de defecto con su historia, la razón con la que el equipo
   etiquetó cada una, y el conocimiento del proyecto en 11 tipos: los del producto
   (reglas, flujos, riesgos, glosario, lecciones, retos, patrones) y los del **oficio**
   (runbooks, datos de prueba, contactos, decisiones). La IA propone; una persona aprueba.
3. **La continuidad** — un **índice por proyecto** que dice cuánto sabe Mnemo de él (con
   su desglose), y un **acta de traspaso firmada** que la consultora puede entregar al
   cliente cuando rota a una persona: qué conocimiento quedó depositado, verificable sin
   cuenta en Mnemo.

## Capacidades

| Capacidad | Módulo | Página |
|---|---|---|
| **Continuidad** — índice por proyecto (4 dimensiones, recalculable) + acta de traspaso firmada | `src/continuity/` | `/app/continuity` |
| **Memoria del proyecto** — 11 tipos de conocimiento, búsqueda semántica unificada con el Defect DNA, propuestas de la IA tras cada ingesta, importación de Confluence por secciones | `src/knowledge/` | `/app/knowledge` |
| **Onboarding** — resumen de dominio, ruta de aprendizaje y preguntas a la memoria con citas | `src/onboarding/` | `/app/onboarding` |
| **Autopilot** — webhook de CI → triaje determinista → acta firmada → gate en el PR | `src/ci/` · `src/triage/` · `src/certify/` | `/app/autopilot` |
| **Defect DNA y calibración** — familias de defecto entre runs y proyectos; la precisión del motor por cliente, medida solo sobre sus predicciones independientes | `src/defects/` | `/app/defects` · `/app/calibration` |
| **Self-heal** — fallo de mantenimiento → parche de selector propuesto → aprobación humana → draft PR (nunca auto-merge) | `src/actions/` | panel de acciones |
| **Plan de pruebas** — HU (texto, URL de Jira o PDF/Word) → plan manual o Gherkin citando la memoria, exportable a Jira-Xray | `src/testplan/` · `src/xray/` | `/app/test-plan` |
| **Automatización** — caso del plan → `.spec.ts` de Playwright con el estilo del repo del cliente → draft PR | `src/automation/` · `src/repo_ingest/` | desde `/app/test-plan` |
| **Grafo y huecos** — relaciones de la memoria + huecos de cobertura (reglas sin test, defectos sin conocimiento, dominios sin lección, riesgos sin mitigación) | `src/graph/` | `/app/graph` |

**Ingesta:** webhook de CI (reporter de Playwright en `packages/`) o subida de informes
con autodetección de 7 formatos (JUnit, TestNG, Robot Framework, Allure, Playwright,
Cypress, Cucumber), más issues de Jira. Idempotente por `run_uid`.

## Las actas, verificables sin cuenta

Tanto el acta de un run (`mnemo.cert.v3`) como el acta de traspaso (`mnemo.traspaso.v1`)
se firman con Ed25519 y se verifican en la página pública `/verify`, vía
`POST /v2/certificates/verify`, u offline con la clave pública
(`GET /v2/certificates/pubkey`). Si alguien retoca el contenido, la firma deja de cuadrar.

Dos invariantes del veredicto, cubiertos por tests: si la IA asistió algún veredicto del
run, el acta nunca es un `apto` rotundo; y sin calibración humana suficiente, tampoco.
Además, si una familia etiquetada como inestable empieza a fallar con una aserción pura,
el motor no la esconde tras la etiqueta: pide revisión humana antes de dar el run por bueno.

## Stack

Python 3.13 · FastAPI · Postgres + pgvector (Supabase) · Supabase Auth (JWT por JWKS) ·
embeddings locales `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, CPU) · LLM
intercambiable (ninguno por defecto · compatible OpenAI · Anthropic · Ollama) · Next.js +
TanStack Query + shadcn/ui · pytest / vitest.

**Sin LLM, Mnemo funciona:** el triaje, las actas, el índice de continuidad y la búsqueda
son deterministas; las funciones de IA degradan (p. ej. una pregunta devuelve sus fuentes
en vez de una respuesta redactada). Los proveedores externos exigen
`ALLOW_EXTERNAL_LLM=true`, porque envían datos de los fallos a un tercero.

## Documentación

| Doc | Contenido |
|---|---|
| [`docs/functional/overview.md`](docs/functional/overview.md) | Qué es, para quién y qué capacidades tiene |
| [`docs/vision/qa-continuity-ai.md`](docs/vision/qa-continuity-ai.md) | Visión, principios y roadmap |
| [`docs/technical/arquitectura.md`](docs/technical/arquitectura.md) | Arquitectura, módulos y flujo de datos |
| [`docs/technical/modelo-datos.md`](docs/technical/modelo-datos.md) | Esquema y aislamiento multi-tenant (RLS) |
| [`docs/technical/api.md`](docs/technical/api.md) | Referencia de endpoints `/v2` |
| [`docs/deploy/produccion.md`](docs/deploy/produccion.md) | Despliegue de frontend, backend y BD |
| [`docs/demo/guion.md`](docs/demo/guion.md) · [`runbook.md`](docs/demo/runbook.md) | Guion de la demo y su operativa |

## Puesta en marcha

1. **Dependencias:** `pip install -r requirements.txt`.
2. **BD (Supabase):** `DATABASE_URL` (Session pooler) + `SUPABASE_URL` / `SUPABASE_JWKS_URL`
   en `.env`; aplicar **todas** las migraciones de `db/migrations/` en orden.
3. **LLM (opcional):** sin configurar, no hay LLM y todo degrada. Para activarlo, ver la
   sección LLM de [`.env.example`](.env.example).
4. **Backend:** `uvicorn asgi:app`.
5. **Frontend:** `cd frontend && npm install && npm run build` (proxy `/api/v2/*` →
   `NEXT_PUBLIC_API_BASE_URL`).
6. **Datos de demo (opcional):** `python3 scripts/docker_init.py`.

Variables por función (todas en [`.env.example`](.env.example)): actas firmadas →
`MNEMO_SIGNING_PRIVATE_KEY` / `_PUBLIC_KEY`; webhook de CI → `CI_WEBHOOK_SECRET` +
`CI_SERVICE_USER_ID`; integraciones Jira/Xray → `MNEMO_SECRET_KEY`; gate y draft PR →
`GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY`.

## Despliegue

- **Frontend (Next.js) → Vercel.** Root Directory = `frontend`; Node 22.x (`frontend/.nvmrc`).
- **Backend (FastAPI) → contenedor Docker** (`Dockerfile`). La demo corre en un Hugging Face
  Space; `render.yaml` documenta la alternativa en Render. El embedder necesita ~1,5 GB de RAM.
- **BD y Auth → Supabase.** Guía completa: [`docs/deploy/produccion.md`](docs/deploy/produccion.md).

## Tests

```bash
python3 -m pytest -m "not integration"   # unitarios (sin BD ni LLM) — lo que corre el CI
python3 -m pytest -m integration         # integración — OJO: corre contra la BD de DATABASE_URL
cd frontend && npm run check:ci          # lint + vitest + build (lo que corre el CI)
```
