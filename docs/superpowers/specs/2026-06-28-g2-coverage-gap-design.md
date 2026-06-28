# QA Continuity AI · G2: Coverage Gap real — diseño

**Fecha:** 2026-06-28 · **Parte de:** [Roadmap de cierre de gaps](../../vision/qa-continuity-gaps-roadmap.md), fase **G2** · **Base:** `main` dbe563b (G1 incluido) · **Backend:** Python/FastAPI · **Frontend:** Next.js/TS.

## Objetivo

Hacer real la funcionalidad estrella "Knowledge Gap Detector": detectar **conocimiento de QA testeable que NO tiene un test que lo cubra**, cruzando `qa_knowledge` (reglas/flujos/riesgos) × `test_assets` (los tests reales del repo, indexados en G1). Hoy el Coverage Gap (F2) solo mira la memoria; G2 lo cruza con los tests reales. Extiende el `detect_gaps` existente — mismo endpoint y mismo panel.

## Decisiones (confirmadas)

- **Medida de cobertura: semántica** — para cada conocimiento testeable, la **distancia cosine mínima** a cualquier `test_asset` del org (`embedding <=> embedding`, en SQL); si supera un **umbral** (o no hay test similar) → "sin test".
- **Sin tests indexados** (org con 0 `test_assets`) → **un único aviso** "indexa el repo primero" (no N falsos gaps).
- **Conocimiento testeable:** `kind ∈ (regla_negocio, flujo, riesgo)`. `glosario/leccion/reto/patron` se excluyen.
- **Determinista** (el cruce es SQL/cosine); el LLM solo redacta la `recommendation` (patrón de F2, degrada). **Sin migración** (cruza tablas existentes). Multi-tenant (membership + RLS; el pooler bypassa RLS → cada query filtra `org_id` + `_is_member`).

## Componentes

### 1. Detector de cobertura (`src/graph/gaps.py`, extender)
Un detector nuevo dentro de `_detect_gaps_inner` (mismo patrón que los 3 actuales):
- **Si `count(test_assets where org_id)` == 0** → emitir **un** gap `{kind: "repo_no_indexado", title: "El repositorio no tiene tests indexados", severity: "media", affected: [], recommendation: "Indexa los tests del repo desde /app/integrations para detectar huecos de cobertura reales."}` y NO evaluar regla-por-regla.
- **Si hay tests** → SQL de cruce:
  ```sql
  select k.id::text, k.title, k.kind,
         (select min(k.embedding <=> t.embedding) from public.test_assets t where t.org_id = %s) as best_dist
  from public.qa_knowledge k
  where k.org_id = %s and k.kind in ('regla_negocio','flujo','riesgo') and k.embedding is not null
  ```
  Por cada fila con `best_dist IS NULL` **o** `best_dist > _COVERAGE_THRESHOLD` → gap `{kind: "regla_sin_test", title: k.title, severity: <por kind>, affected: [k.id], recommendation: <LLM/fallback>}`.
- **`_COVERAGE_THRESHOLD`**: constante (≈`0.55` de distancia cosine; conservador, documentado como calibrable — pgvector `<=>` da 0=idéntico … 2=opuesto; un test que cubre una regla suele quedar ≈0.2-0.4).
- **Severidad:** `riesgo` → `alta`; `regla_negocio`/`flujo` → `media`.
- `recommendation`: `_recommendation("regla_sin_test", title, provider)` (LLM, degrada a `_FALLBACK_REC["regla_sin_test"]`); añadir el fallback fijo del nuevo kind.

### 2. Endpoint / API
Ninguno nuevo: los gaps de G2 salen por el `GET /v2/graph/gaps` existente (ya llama a `detect_gaps`). Membership/degradación heredados.

### 3. Frontend (`/app/graph`, panel de Coverage Gaps)
El panel ya renderiza los gaps por `kind`/`severity`/`title`/`recommendation`/`affected`. Añadir solo: un **label legible** por kind (mapa `regla_sin_test → "Regla sin test"`, `repo_no_indexado → "Repo sin indexar"`, y los kinds de F2) para que el nuevo gap se muestre con un título claro; si el panel ya es genérico, el cambio es mínimo (solo el mapa de etiquetas). Sin cambios de layout.

## Garantías

- **Reusa:** el patrón de `detect_gaps`/`_recommendation`/severidad (F2), los embeddings de `qa_knowledge` y `test_assets` (G1), el endpoint y el panel existentes.
- **Determinista:** el cruce es SQL cosine; el LLM solo redacta. Degrada (sin LLM → fallback; sin tests → el aviso).
- **Multi-tenant:** el cruce filtra `org_id` en ambas tablas + `_is_member` antes de leer.
- **Sin migración** ni endpoint ni tabla nuevos.

## Testing

- **Backend** (`tests/test_graph_gaps.py`, extender): con fixtures (qa_knowledge testeable + test_assets con embeddings) — una regla **con** un test cercano (dist < umbral) NO genera gap; una regla **sin** test cercano (dist > umbral) → `regla_sin_test` con la severidad por kind; `riesgo` → `alta`; 0 `test_assets` → un único `repo_no_indexado` (no N gaps); no-miembro → `[]`; el LLM mockeado para la recommendation + degradación. `python3 -m pytest -m "not integration"` + integración del cruce si aplica.
- **Frontend (vitest):** el panel muestra un gap `regla_sin_test` con su label y severidad; y el aviso `repo_no_indexado`. `npm run lint:ci` + `test` + `tsc` + `build`.

## Verificación local = CI (obligatoria antes de pushear)
Frontend `npm run lint:ci` + `test` + `build`; backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= pytest -m "not integration"; mv .env.bak .env`).

## Fuera de alcance
- Calibración automática del umbral (constante fija ahora; futura: por org/feedback).
- "Test huérfano" (test sin regla asociada) — inverso del gap; futuro.
- Generar el test que falta — eso es **G5** (Automation), que consumirá estos gaps + los `test_assets`.
