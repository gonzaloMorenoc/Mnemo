# QA Continuity AI · G2 (Coverage Gap real) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detectar conocimiento de QA testeable (regla/flujo/riesgo) sin un test que lo cubra, cruzando `qa_knowledge` × `test_assets` por similitud semántica.

**Architecture:** T1 extiende `detect_gaps` con el cruce SQL (determinista). T2 añade el label legible del tipo de gap en el panel de `/app/graph`.

**Tech Stack:** Python/pytest · Postgres/pgvector · Next.js/TS/vitest.

## Global Constraints

- **Determinista:** el cruce es SQL cosine (`embedding <=> embedding`); el LLM SOLO redacta la `recommendation` (patrón existente `_recommendation`, degrada a `_FALLBACK_REC`).
- **Multi-tenant (el pooler bypassa RLS):** el cruce filtra `org_id` en AMBAS tablas y va tras `_is_member` (ya garantizado dentro de `_detect_gaps_inner`).
- **Sin migración / sin endpoint nuevos:** extiende `detect_gaps`; sale por el `GET /v2/graph/gaps` y el panel existentes.
- `_COVERAGE_THRESHOLD = 0.55` (distancia cosine; constante calibrable, documentada). Conocimiento testeable: `kind ∈ (regla_negocio, flujo, riesgo)`. Severidad: `riesgo`→`alta`, `regla_negocio`/`flujo`→`media`.
- **Verificación local = CI por tarea:** frontend `npm run lint:ci`+`test`+`tsc`+`build`; backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= python3 -m pytest -m "not integration" -q; mv .env.bak .env`). **No git worktree.** Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Detector de cobertura real en `detect_gaps`

**Files:** Modify `src/graph/gaps.py`; Test `tests/test_graph_gaps.py`.

**Interfaces:** Consumes — `_connect`/`_is_member`/`_recommendation`/`_FALLBACK_REC` (existentes). Produces — dos kinds nuevos en la lista de `detect_gaps`: `regla_sin_test` y `repo_no_indexado`.

- [ ] **Step 1: Write the failing tests** (extender `tests/test_graph_gaps.py`, mismo estilo de mock de conexión que los tests actuales): (a) un `qa_knowledge` `regla_negocio` cuyo `min(embedding<=>test)` < 0.55 → NO aparece como gap; (b) una `regla_negocio` con `best_dist` 0.8 (>umbral) → gap `regla_sin_test` severity `media`; (c) un `riesgo` sin test cercano → `regla_sin_test` severity `alta`; (d) `count(test_assets)`==0 → exactamente UN gap `repo_no_indexado` (y NINGÚN `regla_sin_test`); (e) no-miembro → `[]`; (f) `generate_structured` mockeado para la recommendation y, con None, cae a `_FALLBACK_REC["regla_sin_test"]`.

- [ ] **Step 2: Run, expect FAIL.** `python3 -m pytest tests/test_graph_gaps.py -q`

- [ ] **Step 3: Implement** en `src/graph/gaps.py`:
  - Añadir a `_FALLBACK_REC`:
    ```python
    "regla_sin_test": (
        "No hay un test que cubra este conocimiento. Genera un caso de prueba "
        "(o automatízalo) para esta regla/flujo/riesgo."
    ),
    "repo_no_indexado": (
        "Indexa los tests del repositorio desde /app/integrations para detectar "
        "huecos de cobertura reales (regla/flujo/riesgo sin test)."
    ),
    ```
  - Constante (junto a las demás): `_COVERAGE_THRESHOLD = 0.55  # distancia cosine; calibrable`.
  - SQL del cruce (constante a nivel de módulo):
    ```python
    _SQL_REGLA_SIN_TEST = (
        "select k.id::text as id, k.title, k.kind,"
        " (select min(k.embedding <=> t.embedding) from public.test_assets t"
        "  where t.org_id = %s and t.embedding is not null) as best_dist"
        " from public.qa_knowledge k"
        " where k.org_id = %s and k.kind in ('regla_negocio','flujo','riesgo')"
        " and k.embedding is not null"
    )
    ```
  - En `_detect_gaps_inner`, dentro del `with _connect(...)` (tras los 3 `cur.execute` actuales):
    ```python
    cur.execute("select count(*) as n from public.test_assets where org_id=%s", (org_id,))
    n_tests = cur.fetchone()["n"]
    coverage_rows = []
    if n_tests > 0:
        cur.execute(_SQL_REGLA_SIN_TEST, (org_id, org_id))
        coverage_rows = cur.fetchall()
    ```
  - Después del bloque que arma `gaps` (antes del `return gaps`):
    ```python
    if n_tests == 0:
        gaps.append({
            "kind": "repo_no_indexado",
            "title": "El repositorio no tiene tests indexados",
            "severity": "media",
            "affected": [],
            "recommendation": _FALLBACK_REC["repo_no_indexado"],
        })
    else:
        for row in coverage_rows:
            best = row.get("best_dist")
            if best is None or best > _COVERAGE_THRESHOLD:
                sev = "alta" if row["kind"] == "riesgo" else "media"
                gaps.append({
                    "kind": "regla_sin_test",
                    "title": row["title"],
                    "severity": sev,
                    "affected": [row["id"]],
                    "recommendation": _recommendation("regla_sin_test", row["title"], provider),
                })
    ```

- [ ] **Step 4: Run PASS** + backend-no-`.env` gate green (`rc=0`, `.env` restaurado).
- [ ] **Step 5: Commit** `feat(graph): coverage gap real (regla_sin_test cruzando qa_knowledge × test_assets)` + trailer.

---

## Task 2: Label del tipo de gap en el panel `/app/graph`

**Files:** Modify `frontend/src/app/app/graph/page.tsx`; Test (su test existente / nuevo).

- [ ] **Step 1: Read** `frontend/src/app/app/graph/page.tsx` — hoy cada gap card muestra `severity` (badge) + `title` + `recommendation` + `affected`, pero NO el `kind`. Añade un **label legible del tipo**.
- [ ] **Step 2: Add** un mapa de labels por kind y renderízalo en cada card (junto al título o como un badge secundario):
  ```tsx
  const GAP_KIND_LABEL: Record<string, string> = {
    regla_sin_test: "Regla sin test",
    repo_no_indexado: "Repo sin indexar",
    defecto_sin_conocimiento: "Defecto sin conocimiento",
    dominio_sin_leccion: "Dominio sin lección",
    riesgo_sin_mitigacion: "Riesgo sin mitigación",
  };
  // en la card:
  <span className="text-xs text-zinc-500" data-testid={`gap-kind-${gap.kind}`}>
    {GAP_KIND_LABEL[gap.kind] ?? gap.kind}
  </span>
  ```
  Mantén el layout; solo añade el label.
- [ ] **Step 3: Test** (vitest, en el test de la página de graph): un gap `{kind:"regla_sin_test", severity:"alta", title:"...", recommendation:"...", affected:["k1"]}` se renderiza con el label "Regla sin test"; un `{kind:"repo_no_indexado", ...}` con "Repo sin indexar".
- [ ] **Step 4: Run** `npm run lint:ci` + `npm test` + `tsc --noEmit` + `npm run build` (todo verde). **Commit** `feat(graph): label legible del tipo de gap en el panel` + trailer.

---

## Notas de cierre
- **Orden:** T1 (detector) → T2 (label). T2 es independiente pero el label cubre también los kinds de T1.
- **Reusa:** `detect_gaps`/`_recommendation`/`_FALLBACK_REC`/severidad (F2), los embeddings de `qa_knowledge` + `test_assets` (G1), el endpoint y el panel.
- **Determinista + degrada:** cruce SQL; sin LLM → fallback; sin tests → el aviso `repo_no_indexado`.
- **Sin migración / endpoint / tabla.** Verificación local=CI por tarea.
- **Fuera de alcance:** calibración automática del umbral; "test huérfano"; generar el test que falta (eso es G5).
