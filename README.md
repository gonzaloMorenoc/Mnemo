# Mnemo · QA Memory

[![Backend CI](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/gonzaloMorenoc/Mnemo/actions/workflows/frontend-ci.yml)

## Pruébalo

- **App:** <https://mnemo-beta-one.vercel.app>
- **Verificación pública de actas, sin cuenta:** <https://mnemo-beta-one.vercel.app/verify>
- **Un acta de traspaso real, lista para verificar:** [acta María → Pablo de `checkout-suite`](https://mnemo-beta-one.vercel.app/verify#v1.eyJjYW5vbmljYWxfanNvbiI6eyJjb250ZW5pZG8iOnsibiI6MjYsInBvcl90aXBvIjp7ImNvbnRhY3RvIjoyLCJkYXRvX3BydWViYSI6MiwiZGVjaXNpb24iOjIsImZsdWpvIjoxLCJnbG9zYXJpbyI6MiwibGVjY2lvbiI6MSwicGF0cm9uIjozLCJyYXpvbl9ldGlxdWV0YSI6NCwicmVnbGFfbmVnb2NpbyI6MywicmV0byI6Miwicmllc2dvIjoyLCJydW5ib29rIjoyfSwic2hhMjU2IjoiMDhkMGE4NTgxY2QzMGFiYTc4OWE5ZjU3ZGE0ODZjMjgwM2FlYWNjNzhiMDhjYWFjMmUzZGU5N2RhMmFiNTY0MSJ9LCJjb250aW51aXR5Ijp7ImRpbWVuc2lvbnMiOlt7ImRlbiI6Mywia2V5IjoibWVtb3JpYV9kZWZlY3RvcyIsImxhYmVsIjoiTWVtb3JpYSBkZSBkZWZlY3RvcyIsIm51bSI6MiwicmF0aW8iOjAuNjY2Nywid2VpZ2h0IjowLjM1fSx7ImRlbiI6NCwia2V5IjoicmF6b25fZXRpcXVldGFzIiwibGFiZWwiOiJFbCBwb3JxdcOpIGRlIGxhcyBldGlxdWV0YXMiLCJudW0iOjQsInJhdGlvIjoxLjAsIndlaWdodCI6MC4yNX0seyJkZW4iOjQsImtleSI6Im9maWNpbyIsImxhYmVsIjoiT2ZpY2lvIGRlbCBwcm95ZWN0byIsIm51bSI6NCwicmF0aW8iOjEuMCwid2VpZ2h0IjowLjI1fSx7ImRlbiI6NSwia2V5IjoicmVnbGFzX3Jlc3BhbGRhZGFzIiwibGFiZWwiOiJSZWdsYXMgY29uIHJlc3BhbGRvIiwibnVtIjo0LCJyYXRpbyI6MC44LCJ3ZWlnaHQiOjAuMTV9XSwic2NvcmUiOjg1fSwiY3JlYXRlZF9hdCI6IjIwMjYtMTAtMDFUMTc6MTU6MDUuNDIyNTU0KzAwOjAwIiwiZW1pdHRlZF9ieSI6IjM4NWIzMDlmLTFhNDItNDJlNS1hMTRiLTZmNzM0ZjRjODY3YiIsImludmVudGFyaW8iOnsiY29ub2NpbWllbnRvX3Bvcl9raW5kIjp7ImNvbnRhY3RvIjoyLCJkYXRvX3BydWViYSI6MiwiZGVjaXNpb24iOjIsImZsdWpvIjoxLCJnbG9zYXJpbyI6MiwibGVjY2lvbiI6MSwicGF0cm9uIjozLCJyZWdsYV9uZWdvY2lvIjozLCJyZXRvIjoyLCJyaWVzZ28iOjIsInJ1bmJvb2siOjJ9LCJkb21pbmlvcyI6NSwiZXRpcXVldGFzIjo0LCJldGlxdWV0YXNfY29uX3Jhem9uIjo0LCJmYW1pbGlhcyI6NCwiZmFtaWxpYXNfY29uX2xlY2Npb24iOjJ9LCJrZXlfaWQiOiI4ZGFlMWUwNzE3NmY4MWE5IiwibW5lbW9fdmVyc2lvbiI6IjAuNC4wIiwib3JnX2lkIjoiYWI0YmE2YmUtYzlmYS00MzNiLThmZWMtNWEyNjZjY2EzMzgzIiwicHJvamVjdCI6ImNoZWNrb3V0LXN1aXRlIiwic2NoZW1hIjoibW5lbW8udHJhc3Bhc28udjIiLCJ0cmFzcGFzbyI6eyJkZSI6Ik1hcsOtYSAoUUEgc2VuaW9yKSIsInBhcmEiOiJQYWJsbyJ9fSwic2lnbmF0dXJlIjoidURjU0tRelo0TnEvSkE5OG9jc0hBZjNHNjhVNFpFYi82SnBwc2ZIZ25rNkE4ZkQxSHVjc0hUQUdvWnJkdDR2K3hYaTRuVThLRFVLZFJFcFVJTFNaQXc9PSJ9).
  El enlace lleva el acta entera en el fragmento (`/verify#v1.…`): la página comprueba la
  firma Ed25519 contra la clave pública del backend y pinta el sello. Si se retoca un solo
  campo del JSON, la firma deja de cuadrar y la página dice «Firma NO válida».
- **La organización de demostración «Demo MTP»** (datos sembrados) requiere cuenta: pide
  acceso al autor a través de GitHub ([@gonzaloMorenoc](https://github.com/gonzaloMorenoc)).

El backend de la demo corre en un plan gratuito que se duerme por inactividad: la primera
petición puede tardar alrededor de un minuto.

## Qué problema resuelve

En una consultora de QA, los consultores rotan. Cuando la persona que lleva un proyecto se
va, con ella se van cosas que no están escritas en ningún sitio: cómo se levanta el
entorno, con qué datos se prueba, a quién se pregunta cuando el sandbox se cae, y **por
qué** un test que parece inestable en realidad no lo es.

**Mnemo es la memoria de QA del proyecto, la que se queda.** Se alimenta del trabajo de
cada día —cada run del CI se ingiere, se clasifica y se firma—, guarda lo que el equipo
explica al etiquetar un fallo o documentar el oficio del proyecto, y lo devuelve a quien
llega, con la fuente citada. Pensada para consultoras de QA con varios clientes.

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
   cliente cuando rota a una persona: quién se va, quién llega, el índice y la huella de
   todo el conocimiento depositado, verificable sin cuenta en Mnemo.

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

Tanto el acta de un run (`mnemo.cert.v3`) como el acta de traspaso (`mnemo.traspaso.v2`)
se firman con Ed25519 y se verifican en la página pública `/verify`, vía
`POST /v2/certificates/verify`, u offline con la clave pública
(`GET /v2/certificates/pubkey`). Si alguien retoca el contenido, la firma deja de cuadrar.

El acta de traspaso firma, además del índice y su desglose, quién se va y quién llega
(`traspaso {de, para}`) y una **huella del contenido** (`contenido {n, sha256, por_tipo}`):
el SHA-256 de cada elemento de conocimiento depositado y de la razón de cada etiqueta,
combinados en una sola raíz. Mnemo la recalcula después para avisar si lo depositado ha
cambiado desde el acta. Las actas `mnemo.traspaso.v1` emitidas antes siguen verificando:
la verificación no depende del esquema y elige la clave por el `key_id` que va firmado
dentro. Por eso una rotación de clave tampoco invalida lo emitido, siempre que la clave
pública anterior se declare en `MNEMO_SIGNING_RETIRED_PUBLIC_KEYS`.

Dos invariantes del veredicto, cubiertos por tests: si la IA asistió algún veredicto del
run, el acta nunca es un `apto` rotundo; y sin calibración humana suficiente, tampoco.
Además, si una familia etiquetada como inestable empieza a fallar con una aserción pura,
el motor no la esconde tras la etiqueta: pide revisión humana antes de dar el run por bueno.

## Stack

Python 3.13 · FastAPI · Postgres + pgvector (Supabase) · Supabase Auth (JWT por JWKS) ·
embeddings locales `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, CPU) · LLM
intercambiable (ninguno por defecto · compatible OpenAI · Anthropic · Ollama; la demo usa
`openai/gpt-oss-120b` en Groq) · Next.js + TanStack Query + shadcn/ui · pytest / vitest.

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
| [`docs/technical/modelo-datos.md`](docs/technical/modelo-datos.md) | Esquema y aislamiento entre clientes |
| [`docs/technical/api.md`](docs/technical/api.md) | Referencia de endpoints `/v2` |
| [`docs/deploy/produccion.md`](docs/deploy/produccion.md) | Despliegue de frontend, backend y BD |
| [`docs/demo/guion.md`](docs/demo/guion.md) | Guion de la demo (María se va, Pablo llega) |

## Arranque en local

Hace falta un proyecto de Supabase (Postgres con pgvector + Auth). Es la ruta que usamos y
la que cubre el CI.

1. **Dependencias del backend:** `pip install -r requirements.txt`.
2. **Variables del backend:** copia [`.env.example`](.env.example) a `.env` y rellena
   `DATABASE_URL` (cadena del *Session pooler*), `SUPABASE_URL` y `SUPABASE_JWKS_URL`. El
   resto es opcional y va por función (ver abajo).
3. **Migraciones:** todas las de `db/migrations/`, en orden. Son idempotentes:
   ```bash
   for f in db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
   ```
   `python3 scripts/docker_init.py` hace lo mismo y además crea un usuario de demo vía
   GoTrue y siembra datos de ejemplo; necesita también `SERVICE_ROLE_KEY`, `DEMO_EMAIL` y
   `DEMO_PASSWORD` en el `.env`.
4. **Backend:** `uvicorn asgi:app --port 8000`.
5. **Frontend:** copia [`frontend/.env.example`](frontend/.env.example) a
   `frontend/.env.local` (URL del backend + URL y anon key de Supabase) y arranca con
   `cd frontend && npm install && npm run dev` → <http://localhost:3000>. El frontend llama
   a `/api/v2/*` y un proxy de servidor lo reenvía a `NEXT_PUBLIC_API_BASE_URL`.

**Puertos.** En local, `uvicorn` escucha en el 8000, que es lo que trae
`frontend/.env.example`. El contenedor del backend (`Dockerfile`) escucha en
`${PORT:-8080}`: si lo levantas con Docker, apunta `NEXT_PUBLIC_API_BASE_URL` a
`http://localhost:8080`.

Variables por función (todas en [`.env.example`](.env.example)): actas firmadas →
`MNEMO_SIGNING_PRIVATE_KEY` / `_PUBLIC_KEY`; webhook de CI → `CI_WEBHOOK_SECRET` +
`CI_SERVICE_USER_ID`; integraciones Jira/Xray → `MNEMO_SECRET_KEY`; gate y draft PR →
`GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY`; LLM → bloque LLM (sin él, todo degrada).

### Opción avanzada: todo en Docker

`docker-compose.yml` levanta un Supabase mínimo propio (Postgres, GoTrue y Kong en el
8000), Ollama, el backend (8080), el frontend (3000) y un servicio `init` que ejecuta
`scripts/docker_init.py`. Las variables salen de [`.env.docker`](.env.docker), que trae
valores de demostración y hay que pasar explícitamente (Compose solo lee `.env` por
defecto):

```bash
docker compose --env-file .env.docker up --build
```

Es una opción secundaria, no la que usa la demo ni la que se prueba en CI. Conviene
saber que:

- el modelo de Ollama (`LLM_MODEL` de `.env.docker`) no viene descargado; sin él, las
  funciones de IA degradan;
- `.env.docker` no lleva claves de firma, así que las actas quedan desactivadas hasta que
  añadas `MNEMO_SIGNING_PRIVATE_KEY` / `_PUBLIC_KEY` al servicio `backend`;
- el proxy del frontend se ejecuta dentro de su contenedor, donde `localhost:8080` no es
  el backend. Lo más directo es levantar con Compose todo salvo el frontend y arrancar
  este con `npm run dev` en la máquina, con `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080`
  y la URL y anon key de Supabase de `.env.docker`.

## Despliegue

- **Frontend (Next.js) → Vercel.** Root Directory = `frontend`; Node 22.x (`frontend/.nvmrc`).
- **Backend (FastAPI) → contenedor Docker** (`Dockerfile`). La demo corre en un Hugging Face
  Space; `render.yaml` documenta la alternativa en Render. El embedder necesita ~1,5 GB de RAM.
- **BD y Auth → Supabase.** Guía completa: [`docs/deploy/produccion.md`](docs/deploy/produccion.md).

## Tests

```bash
python3 -m pytest -m "not integration"   # unitarios (sin BD ni LLM): lo que corre el CI
python3 -m pytest -m integration         # integración: OJO, corre contra la BD de DATABASE_URL
cd frontend && npm run check:ci          # lint + vitest + build (lo que corre el CI)
```
