# QA Continuity AI · Fase 2 (Knowledge Graph + Coverage Gap) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grafo de conocimiento de QA (derivado) + detector de huecos de cobertura — el foso defensible.

**Architecture:** T1 servicio de grafo (deriva nodos/aristas). T2 detector de gaps (determinista). T3 endpoints. T4 cliente. T5 vista react-flow. T6 página.

**Tech Stack:** Python/FastAPI/pytest · Postgres/pgvector · Next.js/TS/vitest · `@xyflow/react` (react-flow).

## Global Constraints

- **Derivar, no inventar:** el grafo sale de `qa_knowledge` (FKs `defect_family_id`/`run_id`, `domain`, `tags`, `embedding`) + `defect_families`. **Sin migración.** `defect_families` **NO tiene `domain`** → el puente defect↔domain y los gaps por dominio se derivan vía `qa_knowledge` (que liga `domain` + `defect_family_id` + `kind`).
- **Multi-tenant (el pooler bypassa RLS):** TODA query filtra por `org_id` y comprueba pertenencia con `_is_member` ANTES de leer (patrón de `src/knowledge/repository.py`). No-miembro → `{nodes:[],edges:[]}` / `[]`.
- **Gaps deterministas:** `detect_gaps` se calcula con SQL; el LLM SOLO redacta `recommendation` (`generate_structured(on_failure="none")` → degrada a texto fijo). Nada se firma.
- **VERIFICACIÓN local = CI, obligatoria al cerrar cada tarea** (rompió el CI de las 4 PRs previas):
  - Frontend: `npm run lint:ci` (eslint `--max-warnings=0`) **+** `npm test` **+** `npx tsc --noEmit` **+** `npm run build`.
  - Backend SIN `.env` (detecta tests que toquen la BD vía `Depends`): `mv .env .env.bak 2>/dev/null; DATABASE_URL= python3 -m pytest -m "not integration" -q; rc=$?; mv .env.bak .env 2>/dev/null; echo rc=$rc` → `rc=0` y `.env` restaurado.
- Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Servicio de grafo `build_graph`

**Files:** Create `src/graph/__init__.py`, `src/graph/service.py`; Test `tests/test_graph_service.py`.

**Interfaces:** Produces — `GraphService(db_url=DATABASE_URL)` con `build_graph(*, user_id, org_id, focus=None, limit=200) -> dict` (`{"nodes": [...], "edges": [...]}`). Nodo: `{id, type, label, ...}` (`type` ∈ `knowledge|defect|domain`). Arista: `{source, target, relation}` (`relation` ∈ `documenta|pertenece|tag`).

- [ ] **Step 1: Read** `src/knowledge/repository.py` (el patrón `_connect`/`_is_member`/`dict_row`/`register_vector`) y `db/migrations/{018_qa_knowledge,002_assurance}.sql` (columnas).

- [ ] **Step 2: Write the failing test** (`tests/test_graph_service.py`): inyecta una conexión fake (o usa el patrón de mock de los tests de repos) con: 2 knowledge (uno con `defect_family_id=F1` y `domain='facturacion'`, otro con `domain='facturacion'` y un tag compartido), 1 defect family `F1`. Assert: `build_graph` devuelve nodos `knowledge:2 + defect:1 + domain:1`; aristas `documenta` (knowledge→F1), `pertenece` (knowledge→domain), `tag` (knowledge↔knowledge); no-miembro → `{nodes:[],edges:[]}`; `limit` recorta; `focus=<id>` deja solo ese nodo y sus vecinos.

- [ ] **Step 3: Implement** `src/graph/service.py` (mirror `knowledge/repository.py`'s connection/membership pattern):

```python
from typing import Any, Dict, List, Optional
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from src.config import DATABASE_URL


class GraphService:
    def __init__(self, db_url: str = DATABASE_URL):
        self.db_url = db_url

    def _connect(self):
        conn = psycopg.connect(self.db_url, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _is_member(self, cur, org_id: str, user_id: str) -> bool:
        cur.execute("select exists(select 1 from public.memberships"
                    " where org_id=%s and user_id=%s) as ok", (org_id, user_id))
        return bool(cur.fetchone()["ok"])

    def build_graph(self, *, user_id: str, org_id: str, focus: Optional[str] = None,
                    limit: int = 200) -> Dict[str, Any]:
        with self._connect() as conn, conn.cursor() as cur:
            if not self._is_member(cur, org_id, user_id):
                return {"nodes": [], "edges": []}
            cur.execute(
                "select id::text, kind, title, domain, tags, defect_family_id::text"
                " from public.qa_knowledge where org_id=%s order by created_at desc limit %s",
                (org_id, limit))
            krows = cur.fetchall()
            fam_ids = [r["defect_family_id"] for r in krows if r["defect_family_id"]]
            fams = {}
            if fam_ids:
                cur.execute("select id::text, title, occurrence_count from public.defect_families"
                            " where id = any(%s::uuid[]) and (org_id=%s or scope='global')",
                            (fam_ids, org_id))
                fams = {r["id"]: r for r in cur.fetchall()}
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, str]] = []

        def add_node(nid, ntype, label, **extra):
            if nid not in nodes:
                nodes[nid] = {"id": nid, "type": ntype, "label": label, **extra}

        for k in krows:
            add_node(k["id"], "knowledge", k["title"], kind=k["kind"], domain=k.get("domain"))
            if k.get("domain"):
                dom = f"domain:{k['domain']}"
                add_node(dom, "domain", k["domain"])
                edges.append({"source": k["id"], "target": dom, "relation": "pertenece"})
            fid = k.get("defect_family_id")
            if fid and fid in fams:
                add_node(fid, "defect", fams[fid]["title"], count=fams[fid]["occurrence_count"])
                edges.append({"source": k["id"], "target": fid, "relation": "documenta"})
        # tag edges: knowledge que comparten un tag
        by_tag: Dict[str, List[str]] = {}
        for k in krows:
            for t in (k.get("tags") or []):
                by_tag.setdefault(t, []).append(k["id"])
        for ids in by_tag.values():
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    edges.append({"source": ids[i], "target": ids[j], "relation": "tag"})

        if focus:
            keep = {focus} | {e["target"] for e in edges if e["source"] == focus} \
                            | {e["source"] for e in edges if e["target"] == focus}
            nodes = {nid: n for nid, n in nodes.items() if nid in keep}
            edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
        return {"nodes": list(nodes.values()), "edges": edges}
```
(Similitud por `embedding` → `relation:"similar"` queda como mejora futura; no en este PR para acotar el coste de N consultas top-k.)

- [ ] **Step 4: Run** the test (PASS) + the backend-no-`.env` gate (Global Constraints) → `rc=0`.
- [ ] **Step 5: Commit** `feat(graph): build_graph deriva el grafo de conocimiento (qa_knowledge + defect_families)` + trailer.

---

## Task 2: Detector de huecos `detect_gaps`

**Files:** Create `src/graph/gaps.py`; Test `tests/test_graph_gaps.py`.

**Interfaces:** Consumes — `GraphService._connect`/`_is_member` (reusar) o el mismo patrón. Produces — `detect_gaps(*, user_id, org_id, provider=None) -> List[dict]`; cada gap `{kind, title, severity, affected, recommendation}` (`kind` ∈ `defecto_sin_conocimiento|dominio_sin_leccion|riesgo_sin_mitigacion`; `severity` ∈ `alta|media|baja`).

- [ ] **Step 1: Write the failing test** (`tests/test_graph_gaps.py`): fixtures — un `defect_family` del org sin ningún `qa_knowledge` que lo referencie → un gap `defecto_sin_conocimiento` (severity por `occurrence_count`: ≥5 alta, ≥2 media, si no baja); un `domain` con knowledge que tiene `defect_family_id` pero ningún `kind='leccion'` → `dominio_sin_leccion`; un `riesgo`/`regla_negocio` en un dominio sin `leccion`/`patron` → `riesgo_sin_mitigacion`. LLM mockeado para `recommendation`; con `generate_structured`→None la `recommendation` cae a un texto fijo por `kind` (nunca vacío, nunca lanza). No-miembro → `[]`.

- [ ] **Step 2: Implement** `src/graph/gaps.py` — funciones que ejecutan las 3 consultas (membership-gated, patrón `_connect`/`_is_member`):
  - `defecto_sin_conocimiento`: `select f.id, f.title, f.occurrence_count from public.defect_families f where (f.org_id=%s) and not exists (select 1 from public.qa_knowledge k where k.org_id=%s and k.defect_family_id=f.id)`.
  - `dominio_sin_leccion`: dominios con `qa_knowledge` que tienen `defect_family_id is not null` pero el dominio no tiene ninguna fila `kind='leccion'` (group by `domain`).
  - `riesgo_sin_mitigacion`: filas `kind in ('riesgo','regla_negocio')` cuyo `domain` no tiene ninguna `kind in ('leccion','patron')`.
  - `severity` por recurrencia (`occurrence_count`) / número de afectados. `recommendation`: intenta `generate_structured(prompt, context, {"recommendation":""}, on_failure="none")`; si `None`, usa un texto fijo por `kind` (p.ej. "Captura una lección para el defecto recurrente <title>."). Catch-all → el gap se devuelve con la recomendación fija (nunca lanza).

- [ ] **Step 3: Run** test (PASS) + backend-no-`.env` gate → `rc=0`. **Step 4: Commit** `feat(graph): detect_gaps — huecos de conocimiento deterministas (LLM solo redacta)` + trailer.

---

## Task 3: Endpoints `/v2/graph` + `/v2/graph/gaps`

**Files:** Modify `src/api_v2.py`; Test `tests/test_api_v2_graph.py`.

- [ ] **Step 1: Endpoints** (`src/api_v2.py`, GET con query params, `Depends(get_current_user)`; construyen `GraphService()` y llaman `build_graph`/`detect_gaps` con `user_id=user.user_id`):
```python
from src.graph.service import GraphService
from src.graph.gaps import detect_gaps

@router.get("/graph", response_model=Dict[str, Any])
def get_graph(org_id: str, focus: Optional[str] = None, limit: int = 200,
              user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    return GraphService().build_graph(user_id=user.user_id, org_id=org_id, focus=focus, limit=min(limit, 500))

@router.get("/graph/gaps", response_model=List[Dict[str, Any]])
def get_graph_gaps(org_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> List[Dict[str, Any]]:
    return detect_gaps(user_id=user.user_id, org_id=org_id)
```
(`GraphService()`/`detect_gaps` abren su propia conexión; membership lo comprueba el servicio → no-miembro = vacío, sin fuga.)

- [ ] **Step 2: Tests** (`tests/test_api_v2_graph.py`, `dependency_overrides` + monkeypatch `api_v2.GraphService`/`api_v2.detect_gaps`): `/graph` → 200 `{nodes,edges}`; `/graph/gaps` → 200 lista; **401 sin auth**; no-miembro (servicio real con repo fake) → vacío; `limit` se acota a ≤500.

- [ ] **Step 3: Run** PASS + backend-no-`.env` gate → `rc=0`. **Step 4: Commit** `feat(api): endpoints /v2/graph + /v2/graph/gaps` + trailer.

---

## Task 4: Cliente frontend

**Files:** Modify `frontend/src/lib/api/endpoints.ts`, `types.ts`; Test `frontend/src/lib/api/__tests__/graph.test.ts`.

- [ ] **Step 1: Types** (`types.ts`): `GraphNode` ({ id: string; type: "knowledge"|"defect"|"domain"; label: string; kind?: string; domain?: string; count?: number }); `GraphEdge` ({ source: string; target: string; relation: "documenta"|"pertenece"|"tag" }); `Graph` ({ nodes: GraphNode[]; edges: GraphEdge[] }); `CoverageGap` ({ kind: string; title: string; severity: "alta"|"media"|"baja"; affected: string[]; recommendation: string }).
- [ ] **Step 2: Client** (`endpoints.ts`, GET con query, patrón `apiRequest`):
```ts
export function getGraph(token: string, params: { org_id: string; focus?: string; limit?: number }) {
  const q = new URLSearchParams({ org_id: params.org_id });
  if (params.focus) q.set("focus", params.focus);
  if (params.limit) q.set("limit", String(params.limit));
  return apiRequest<Graph>(`/api/v2/graph?${q.toString()}`, "GET", { token });
}
export function getGaps(token: string, params: { org_id: string }) {
  return apiRequest<CoverageGap[]>(`/api/v2/graph/gaps?org_id=${encodeURIComponent(params.org_id)}`, "GET", { token });
}
```
- [ ] **Step 3: Test** (`__tests__/graph.test.ts`, `global.fetch` spy): cada uno pega al path correcto (con los query params) + parsea. Run `npm test -- graph`. Then the frontend CI gate (lint:ci + tsc). **Commit** + trailer.

---

## Task 5: Vista de grafo (react-flow)

**Files:** Modify `frontend/package.json` (+ lockfile); Create `frontend/src/components/graph/knowledge-graph-view.tsx`, its test.

- [ ] **Step 1: Dep.** `npm --prefix frontend install @xyflow/react` (react-flow v12; el CSS se importa en el componente: `import "@xyflow/react/dist/style.css"`).
- [ ] **Step 2: Component** `KnowledgeGraphView({ graph }: { graph: Graph })` (`"use client"`): mapea `graph.nodes` → react-flow nodes (color por `type`: knowledge azul, defect rojo, domain gris; un layout simple — posiciones en rejilla/círculo por índice, o `dagre` si se añade) y `graph.edges` → react-flow edges (con `label = relation`). `<ReactFlow>` con `fitView`, `Controls`, `Background`; click en un nodo → `onNodeClick` resalta el nodo + sus vecinos (estado local `selectedId`, atenúa el resto). Maneja `graph` vacío (mensaje "sin datos").
- [ ] **Step 3: Test** (vitest; react-flow necesita un mock de ResizeObserver/dimensiones — añade el shim en el test o en `vitest.setup`): renderiza con un grafo de 3 nodos → aparecen los labels; click en un nodo no rompe. (Si react-flow es difícil de testear en jsdom, testea la función pura de mapeo `graph→{nodes,edges}` extraída a un helper, + un smoke render.)
- [ ] **Step 4: Run** the frontend CI gate (lint:ci + test + tsc + build). **Commit** `feat(graph): KnowledgeGraphView con react-flow` + trailer.

---

## Task 6: Página `/app/graph` + nav

**Files:** Create `frontend/src/app/app/graph/page.tsx`, its test; Modify `sidebar-nav.tsx` (+ `topbar.tsx`).

- [ ] **Step 1: Page** (`"use client"`, patrón de `knowledge`/`onboarding` page): `useActiveOrg()` (con su `isLoading`) + `useAuth()`. `useQuery(getGraph)` + `useQuery(getGaps)`. Layout: a la izquierda `<KnowledgeGraphView graph={...} />`; a la derecha un **panel de Coverage Gaps** ordenado por severidad (alta→baja), cada uno con un badge de severidad, el `title`, la `recommendation` y los `affected`. Empty state si `!activeOrgId && !isLoading`; "Cargando…" mientras `isLoading`; si el grafo viene vacío → mensaje "Aún no hay conocimiento suficiente". Degrada: error de query → toast, no crash.
- [ ] **Step 2: Nav** (`sidebar-nav.tsx`): `{ href: "/app/graph", label: "Knowledge Graph", icon: <a lucide icon, e.g. Network o Share2> }`; `topbar.tsx` pageTitles `"/app/graph": "Knowledge Graph"`.
- [ ] **Step 3: Test** (vitest, mock auth + `useActiveOrg` + endpoints): la página pide `getGraph`/`getGaps` y renderiza al menos un nodo (o el contenedor del grafo) + un gap del panel con su severidad; sin org → empty state; query rechazada → toast sin crash.
- [ ] **Step 4: Run** the frontend CI gate (lint:ci + test + tsc + build). **Commit** + trailer.

---

## Notas de cierre
- **Orden:** T1 (grafo) → T2 (gaps) → T3 (endpoints) → T4 (cliente) → T5 (vista) → T6 (página). T3 consume T1+T2; T6 consume T4+T5.
- **Reusa:** el patrón `_connect`/`_is_member` de los repos; `generate_structured`; el patrón de página + `useActiveOrg`/`isLoading`.
- **Degradación:** servicio no-miembro → vacío; gaps sin LLM → recomendación fija; página → toast.
- **Sin migración** (deriva de lo existente). **Verificación local = CI** en cada tarea (ver Global Constraints).
- **Fuera de alcance:** aristas `similar` (embedding top-k), tabla de edges manuales, `test_runs` como nodos, gap de tests reales (Fase 3).
