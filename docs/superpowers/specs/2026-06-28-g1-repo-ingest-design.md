# QA Continuity AI · G1: Ingesta del repositorio — diseño

**Fecha:** 2026-06-28 · **Parte de:** [Roadmap de cierre de gaps](../../vision/qa-continuity-gaps-roadmap.md), fase **G1** (el desbloqueador) · **Base:** `main` 72374ef · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

Leer los **tests existentes** del repo del cliente (vía la GitHub App ya configurada por org) e indexarlos en Mnemo. Es el desbloqueador del roadmap: una vez indexados, **G2** detecta el *coverage gap real* (regla/HU sin test) y **G5** genera automatización *al estilo del repo* (el Automation Agent recupera tests reales como few-shot, en vez del `style_sample` que hoy se pega a mano). MVP acotado: **solo tests + indexación**; código fuente/PRs y el coverage-gap/automation que los consumen son fases posteriores.

## Decisiones (confirmadas)

- **Almacenamiento:** tabla nueva **`test_assets`** (no un `kind` de `qa_knowledge`) — un test es una entidad distinta del conocimiento; base limpia para G2 (cruce `qa_knowledge` × `test_assets`) y G4 (grafo).
- **Estilo implícito:** NO se genera ni guarda un "perfil de estilo"; el estilo **son** los tests indexados, que G5 recuperará como few-shot por dominio/semántica.
- **Disparo:** botón **"Indexar tests del repo"** en `/app/integrations` (bajo demanda; full: reemplaza lo indexado de ese repo).
- **Multi-tenant:** `test_assets` con RLS+force+policy `is_org_member`; toda query filtra `org_id` + comprueba pertenencia (el pooler bypassa RLS). Degrada sin config GitHub (503).

## Componentes

### 1. Listar el árbol del repo (`src/ci/github_app.py`)
`GitHubCodeHost.list_tree() -> list[str]`: `GET /repos/{repo}/git/trees/{default_branch}?recursive=1` → rutas de todos los ficheros. Reusa `_headers`/`_session`/`_default_branch`/`_ref_sha`. (Helper `read_file` ya existe para traer el contenido.)

### 2. Tabla `test_assets` (migración `020_test_assets.sql`, aplicada a prod)
`id, org_id (FK organizations), repo_full_name, path, framework, domain, content, embedding vector(384), created_at`. Índices: `(org_id)`, `(org_id, domain)` parcial, ivfflat parcial sobre `embedding`. RLS: `enable` + `force` + policy `test_assets_member using public.is_org_member(org_id)`.

### 3. Repositorio + servicio de indexación (`src/repo_ingest/`)
- `TestAssetRepository` (patrón `QaKnowledgeRepository`): `replace_for_repo(*, user_id, org_id, repo, assets)` (membership-gated; borra los del repo + inserta los nuevos con embedding), `list_assets(*, user_id, org_id)`, `search_semantic(...)` (para G5). 
- `index_repo_tests(*, user_id, org_id, codehost_factory) -> dict`: `list_tree` → filtra **tests** por patrón (`*.spec.ts`, `*.test.ts`, `*.feature`, `*.cy.ts`, y rutas `tests/|e2e/|cypress/|specs/`) → `read_file` con **cota** (máx 200 ficheros, máx 100 KB/fichero) → por cada uno: `framework` (por extensión: playwright/cucumber/cypress), `domain` inferido del path (best-effort: primer segmento significativo), `embedding` del contenido → `replace_for_repo`. Devuelve `{indexed, by_domain, skipped}`. Degrada: sin config GitHub → error claro (503); fichero ilegible → se salta.

### 4. Endpoints (`src/api_v2.py` + modelos)
- `POST /v2/repo/index` (`{org_id}`) → ejecuta `index_repo_tests` (vía `_github_codehost_factory`) → `{indexed, by_domain, skipped}`; **503** sin config GitHub; 502 en error de API.
- `GET /v2/repo/tests` (`org_id`) → lista de `{path, framework, domain}` (sin el `content` completo).
- Ambos `Depends(get_current_user)`, membership-gated.

### 5. Frontend (`/app/integrations` + cliente)
- En la página de integraciones, junto a la config GitHub: botón **"Indexar tests del repo"** → `indexRepo` (`useMutation`) → toast con el resultado (`N tests indexados`, dominios) + una lista/resumen de los tests indexados (`listRepoTests`). Estados: sin config GitHub → aviso "configura GitHub primero"; cargando; degrada (error → toast).
- Cliente: `indexRepo(token, {org_id})`, `listRepoTests(token, {org_id})` + tipo `TestAsset`.

## Garantías

- **Reusa:** `GitHubCodeHost` (+ `list_tree` nuevo), `_github_codehost_factory`, el patrón de repo/embedding de `qa_knowledge`, `LocalEmbedder`, la página de integraciones.
- **Multi-tenant:** `test_assets` RLS + cada query membership-gated; el repo se identifica por la config GitHub del org (cifrada).
- **IA fuera del camino crítico:** la indexación es determinista (listar+leer+embeddings); no usa LLM. Degrada sin GitHub.
- **Acotado:** cotas de nº de ficheros/tamaño; full-replace por repo (incremental = futuro).

## Testing

- **Backend:** `list_tree` (mock del transporte GitHub → rutas); el filtro de patrones (incluye/excluye); `index_repo_tests` (codehost fake → assets con framework/domain/embedding; cota respetada; sin config → error); `TestAssetRepository` (membership: no-miembro → vacío/sin escritura); endpoints (auth/401/membership/200/503). `python3 -m pytest -m "not integration"` + integración para la RLS de `test_assets` (patrón de los tests RLS existentes).
- **Frontend (vitest):** el botón llama `indexRepo` y muestra el resultado; `listRepoTests` renderiza; sin config GitHub → aviso; error → toast. `npm run lint:ci` + `npm test` + `tsc` + `build`.

## Verificación local = CI (obligatoria antes de pushear)
Frontend `npm run lint:ci` + `test` + `build`; backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= pytest -m "not integration"; mv .env.bak .env`). **Migración 020 aplicada a prod** (psql, DATABASE_URL del .env) + verificada (RLS: `relrowsecurity`+`relforcerowsecurity`).

## Fuera de alcance (fases posteriores)
- **Código fuente / PRs** del repo (G1 = solo tests).
- **Coverage Gap real** que cruza reglas × tests (eso es **G2**).
- **Automation desde el estilo del repo** que consume `test_assets` como few-shot (eso es **G5**).
- Indexación **incremental** (por commit/webhook), perfil de estilo explícito, frameworks no-JS/TS.
