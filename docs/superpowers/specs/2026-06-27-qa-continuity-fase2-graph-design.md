# QA Continuity AI · Fase 2: Knowledge Graph + Coverage Gap — diseño

**Fecha:** 2026-06-27 · **Parte de:** [QA Continuity AI](../../vision/qa-continuity-ai.md), Fase 2 (el foso) · **Base:** `main` 00b5a60 (1a+1b+onboarding+automation, CI verde) · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

El **foso defensible** que la [revisión profunda](../../../) señaló: hacer **explícitas las relaciones** entre el conocimiento de QA (Fase 1a) y el Defect DNA, y detectar **huecos de cobertura de conocimiento**. Dos piezas en un PR: un **Knowledge Graph** (grafo visual de nodos+aristas) y un **Coverage Gap Detector** (reporte priorizado de huecos). El grafo se **deriva de lo que ya existe** — no inventa datos.

## Decisiones (confirmadas)

- **Todo en un PR** (grafo + coverage gap).
- **Derivar de lo existente** (sin migración, sin nodos inventados): nodos = items de `qa_knowledge` + `defect_families` (+ `domain` como agrupador); aristas = de las FKs (`defect_family_id`, `run_id`) + `domain`/`tags` compartidos + similitud por `embedding`.
- **Grafo visual interactivo** (react-flow) en el frontend.
- **Coverage Gap = gap de conocimiento sobre la memoria** (factible ya; no requiere los tests reales del repo).
- **Multi-tenant** (membership app-layer en cada query; el pooler bypassa RLS). **IA propone/degrada** (la detección de gaps es determinista; el LLM solo redacta/prioriza y degrada).

## Componentes

### 1. Grafo derivado (`src/graph/service.py`)
`build_graph(*, user_id, org_id, focus=None, limit=200) -> dict` → `{nodes, edges}`, todo membership-gated por `org_id`:
- **Nodos:** `qa_knowledge` (`{id, type:"knowledge", kind, title, domain}`), `defect_families` (`{id, type:"defect", label, count}`), y `domain` como nodo agrupador (`{id:"domain:<d>", type:"domain", label}`).
- **Aristas:** `knowledge→defect` (vía `defect_family_id`, relación `documenta`); `knowledge→domain` y `defect→domain` (relación `pertenece`); `knowledge↔knowledge` por `tags` compartidos (relación `tag`); `knowledge↔knowledge` por similitud de `embedding` top-k (relación `similar`, opcional).
- **Cota:** `limit` nodos (por recencia/relevancia) para no saturar la vista; `focus` opcional centra el grafo en una entidad y sus vecinos.

### 2. Coverage Gap Detector (`src/graph/gaps.py`)
`detect_gaps(*, user_id, org_id, provider=None) -> list[dict]` — **determinista** (consultas SQL sobre el grafo), membership-gated; cada gap `{kind, title, severity (alta|media|baja), affected (ids), recommendation}`:
- **Defecto sin conocimiento:** `defect_families` sin ningún `qa_knowledge` que lo referencie (`defect_family_id`). Severidad por recurrencia/`count`.
- **Dominio con defectos sin lección:** un `domain` con `defect_families` pero sin `qa_knowledge` de `kind='leccion'`.
- **Riesgo/regla sin mitigación:** `kind in ('riesgo','regla_negocio')` sin una `leccion`/`patron` vinculada en el mismo dominio.
- La **recomendación** la redacta el LLM (opcional, `generate_structured` degradando a un texto determinista por `kind`); la **detección** nunca depende del LLM.

### 3. Endpoints (`src/api_v2.py` + modelos)
- `GET /v2/graph` (`org_id`, `focus?`, `limit?`) → `{nodes, edges}`.
- `GET /v2/graph/gaps` (`org_id`) → `[gap, ...]`.
- Ambos `Depends(get_current_user)`, membership-gated (las queries filtran por `org_id` + comprobación de pertenencia, igual que el repo de 1a).

### 4. Frontend (`/app/graph` + cliente + nav)
- Página **Knowledge Graph**: a la izquierda, la **vista de grafo interactiva** (react-flow — nueva dependencia): nodos coloreados por tipo (knowledge / defect / domain), aristas etiquetadas por relación, zoom/pan, click en un nodo → resalta vecinos. A la derecha, el **panel de Coverage Gaps**: lista priorizada por severidad con la recomendación y un enlace a la entidad. `useActiveOrg`; empty state sin org / sin datos; degrada (fallo de red → toast).
- Cliente: `getGraph(token, {org_id, focus?})`, `getGaps(token, {org_id})` + tipos `GraphNode`/`GraphEdge`/`Graph`/`CoverageGap`. Nav: entrada "Knowledge Graph".

## Garantías

- **Reusa, no inventa:** el grafo se deriva de `qa_knowledge` (FKs/domain/tags/embedding) + `defect_families`; **sin migración**.
- **Multi-tenant:** cada query filtra por `org_id` con comprobación de pertenencia (el pooler bypassa RLS).
- **IA propone/degrada:** los gaps se **detectan deterministamente** (SQL); el LLM solo redacta la recomendación y degrada a texto fijo; nada se firma.
- **Acotado:** `limit` en nodos/aristas para que la vista no se sature.

## Testing

- **Backend:** `build_graph` (con un repo fake → nodos/aristas correctos: FK→`documenta`, domain→`pertenece`, tags→`tag`; respeta `limit` y `focus`; membership → vacío para no-miembro); `detect_gaps` (fixtures: defecto sin conocimiento → gap; dominio con defecto sin lección → gap; severidad por recurrencia; LLM mockeado para la recomendación + degradación); endpoints (auth/401/membership/200/estructura). `python3 -m pytest -m "not integration"` (+ integración sobre prod si aplica).
- **Frontend (vitest):** la página pide `getGraph`/`getGaps` y renderiza nodos + el panel de gaps; click en un nodo; degrada si falla. `npm run lint:ci` + `npm test` + `tsc` + `build`.

## Verificación local = CI (obligatorio antes de pushear)

Replicar el CI: frontend `npm run lint:ci` (eslint `--max-warnings=0`) + `test` + `build`; backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= pytest -m "not integration"; mv .env.bak .env`) para detectar tests que toquen la BD. Ver [[mnemo-ci-local-verification]].

## Fuera de alcance

- **Tabla de edges manuales / inferidos por IA** (vínculos que el usuario añade) — el grafo aquí es 100% derivado.
- **Gap de cobertura de tests reales** del repo — requiere la ingesta de Fase 3.
- `test_runs` como nodos del grafo (se evita saturar; las aristas `run_id` quedan para una iteración futura).
