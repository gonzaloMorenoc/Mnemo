# Auditoría de Arquitectura y Calidad de Código — Mnemo Autopilot

**Fecha:** 2026-06-26 · **Rama:** `main` (`6929d77`, al día) · **Alcance:** salud arquitectónica y deuda técnica tras el **Bloque B** (5 PRs de IA: `src/ai/` + `root_cause` + `ai_repair`).
**Escala medida:** 96 archivos `.py` / **7253 líneas** en `src/` (media **~75 líneas/archivo**), 111 archivos de test, 17 migraciones SQL.
**Método:** solo lectura. Toda afirmación lleva evidencia `archivo:línea`. Esfuerzo: S<½d · M≈1-2d · L>2d.

> Esta auditoría es complementaria a `2026-06-25-auditoria-profunda.md` (seis dimensiones). Aquí me concentro en **arquitectura/calidad** y en el **estado del Bloque B**, y verifico qué deuda previa se pagó y cuál creció.

---

## 1. Veredicto

**La base aguanta crecer — con una salvedad estructural que hay que cortar antes de la demo.** B+ tirando a A− en el **motor Autopilot** (`triage/`, `actions/`, `certify/`, `defects/`, `ai/`): fronteras limpias por inyección de dependencias, sin fugas de capa, degradación IA homogénea, e inmutabilidad respetada. El **Bloque B está bien factorizado**: `ai/generate.py::generate_structured` es una base real de 50 líneas reusada sin duplicación por judge/nl_query/briefing/root_cause/ai_repair.

**La salvedad:** el contenedor de producción **arranca la app legacy** (`Dockerfile` → `uvicorn api:app`), y `api.py` carga ansiosamente todo el RAG legacy (`LogLoader`, `VectorStoreManager`, `BugAnalyzer`, `RAGASEvaluator`) en `startup_event` y expone endpoints legacy **sin autenticación** (`/analyze`, `/sync`, `/history`, `/evaluate`). El motor Autopilot vive como un `include_router(v2_router)` **colgado de la app vieja**. No es deuda muerta: es deuda **viva y en el arranque**. Esto, más dos God-objects que **crecieron** desde la auditoría anterior (no se pagó M1/M2), es lo que baja la nota global.

**Resumen de salud por zona:**

| Zona | Nota | Comentario |
|------|------|-----------|
| `src/ai/` (Bloque B) | **A** | Base reusada, sin duplicación, degradación uniforme. |
| Motor Autopilot (`triage`/`actions`/`certify`) | **A−** | Cohesión alta, DI limpia, archivos pequeños. |
| Frontera/entrypoint (`api.py` + legacy) | **C** | App legacy es el entrypoint de prod; RAG legacy en el boot, sin auth. |
| `defects/repository.py` + `api_v2.py` | **C+** | God-objects que crecieron (988 / 974 líneas). |
| Consistencia de patrones (DB/constantes) | **B−** | `_connect`/`_set_claims` ×5, `_CATEGORIES` ×5, guard inline ×36. |

---

## 2. Archivos grandes y cohesión

### 2.1 Los dos God-objects — y la señal de alarma: **crecieron**

| Archivo | Líneas hoy | En auditoría 25-jun | Δ |
|---------|-----------:|--------------------:|---|
| `src/defects/repository.py` | **988** | 952 (M1) | **+36** |
| `src/api_v2.py` | **974** | 891 (M2) | **+83** |
| `src/tenant_kb.py` | 505 | — | — |

El dato importante no es el tamaño absoluto, es la **tendencia**: la auditoría anterior marcó ambos como deuda a refactorizar (M1/M2) y el Bloque B **añadió encima** en vez de partirlos. Si el patrón sigue, en el próximo bloque rebasan el límite duro de 800 que exige el estilo del proyecto (ya lo rebasan: 988 y 974 > 800).

**`src/defects/repository.py` (988 líneas, 19 métodos públicos) — God Repository.** Una sola clase `AssuranceRepository` mezcla cinco responsabilidades:
- **Ingesta + matching de familias:** `ingest_run`, `ingest_ci_run`, `_match_and_insert_failure`, `_query_candidates` (líneas 99-334).
- **Lectura de familias/linaje:** `list_defects`, `get_lineage`, `get_family_with_failures`, `search_families_semantic` (350-502, 928-951).
- **Triaje (datos):** `get_triage_inputs`, `save_triage_verdicts`, `get_triage_for_run`, `update_triage_verdict`, `get_run_actionable_verdicts` (636-926).
- **Calibración/foso:** `set_family_label`, `get_calibration_metrics` (832-897).
- **Contexto self-heal:** `get_selfheal_context` (953-988).

Es el "1 archivo grande" que contradice el principio "muchos archivos pequeños". El método más largo, `get_triage_inputs` (636-744, ~108 líneas), supera el umbral de 50 líneas/función del estilo. **Acopla**: lo consumen por DI `certify/service.py`, `certify/gate.py`, `ci/ingestion_service.py`, `jira/ingestion_service.py` y 11 endpoints de `api_v2.py` — el split es mecánico pero toca varios sitios de cableado.
**Fix (M, ~2d):** extraer `TriageRepository` (636-926) y `CalibrationRepository` (832-897); `AssuranceRepository` queda con ingesta+familias. Compartir conexión vía un `BaseRepository` (ver §4.1).

**`src/api_v2.py` (974 líneas, 33 endpoints, 16 singletons) — router monolítico.** Un único `APIRouter` cubre org, ingest, CI webhook, triaje, integraciones (Jira/GitHub), defectos, calibración, root-cause, assurance, acciones, certificados, gate, ask, briefing. Las **líneas 94-314** son 16 singletons perezosos + 2 factories + 2 wrappers Lazy — todo el grafo de dependencias del sistema en un archivo. Mezcla además dos generaciones: el endpoint legacy `/analyze` (325-359, vía `tenant_kb` + `structured_analyzer`) conive con los endpoints Autopilot.
**Fix (M, ~1d):** `dependencies.py` para los singletons; sub-routers por dominio (`routers/org.py`, `routers/actions.py`, `routers/certify.py`, …); `api_v2` queda como agregador.

### 2.2 Lo que sí respeta "archivos pequeños"

El **resto del repo es ejemplar**: media de ~75 líneas/archivo. `src/ai/` (generate 55, judge 61, nl_query 36, briefing 82), `triage/` (engine 47, service 89, tiebreaker 62, signals, patterns…), `actions/selfheal/` (7 archivos, todos <103 líneas), `ingest/` (un parser por formato, ~30-60 líneas c/u). La descomposición por feature/dominio es correcta. **Los dos God-objects son la excepción, no la regla** — y por eso son fáciles de aislar y pagar.

---

## 3. Legacy vs Autopilot — **el hallazgo nº1 de esta auditoría**

Hay **dos apps FastAPI** y el RAG legacy está **mal aislado por el entrypoint**, aunque sí esté desacoplado a nivel de imports del motor.

### 3.1 El mapa real

**Entrypoint de producción = la app legacy.** `Dockerfile`:
```
COPY api.py .
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
```
`api.py` (135 líneas) es la app de "Smart Error Debugger" (RAG legacy):
- `api.py:32` monta el Autopilot como sub-router: `app.include_router(v2_router)`.
- `api.py:42-58` `initialize_system()` en `@app.on_event("startup")` instancia **ansiosamente** `LogLoader`, `VectorStoreManager`, `BugAnalyzer(vectorstore)`, `RAGASEvaluator()`, `DatabaseInspector()`. **Cada arranque del contenedor carga la pila RAG legacy completa** (RAGAS arrastra dependencias pesadas) aunque no se use.
- `api.py:60-127` expone `/analyze`, `/sync`, `/history`, `/stats`, `/evaluate` **sin `Depends(get_current_user)`** — endpoints sin auth, multitenant-blind, en el mismo proceso que el `/v2` securizado.

`main.py` (54 líneas) es un **segundo** entrypoint: REPL CLI legacy (`from src.loader/vector_store/model/inspector`). No se despliega, pero versiona ruido.

### 3.2 Grafo de imports (qué está realmente enredado)

| Módulo legacy | Líneas | ¿Lo importa el Autopilot? | Tests | Veredicto |
|---------------|-------:|---------------------------|:-----:|-----------|
| `vector_store.py` | 60 | No | 0 | **Muerto** (solo `api.py`/`main.py`) |
| `loader.py` | 131 | No | 0 | **Muerto** (solo `api.py`/`main.py`) |
| `model.py` | 25 | No | 0 | **Muerto** (importa `retriever`+`prompts`) |
| `retriever.py` | 58 | No (solo `model.py`) | 0 | **Muerto** |
| `prompts.py` | 20 | No (solo `model.py`) | 0 | **Muerto** |
| `inspector.py` | 36 | No | 0 | **Muerto** |
| `history.py` | 81 | No | 0 | **Muerto** |
| `evaluator.py` (RAGAS) | 121 | No | 1 | **Muerto** salvo el `/evaluate` legacy |
| `structured_analyzer.py` | 95 | **Sí** (`api_v2.py:86`, `/analyze`) | sí | **Vivo, legacy** — endpoint `/v2/analyze` aún usa el RAG viejo |
| `tenant_kb.py` | 505 | **Sí** (`api_v2.py:87`) | sí | **MIXTO — no borrar** (ver abajo) |
| `sanitizer.py` | 130 | **Sí** (3 ingestion services) | sí | **Vivo, compartido** — NO es legacy, es reuso correcto |
| `scope_priority.py` | — | Sí (`tenant_kb`) | sí | Vivo (soporta `tenant_kb`) |

**Matiz crítico sobre `tenant_kb.py`:** no se puede borrar de un plumazo. Contiene **dos cosas**: (a) el RAG legacy de `/v2/analyze` (`retrieve_context`, `save_analysis`, `ingest_file`) y (b) la **CRUD de orgs/membership que el Autopilot necesita** (`create_organization`, `join_organization`, `list_user_organizations` — `api_v2.py:378-427`). El alta de organización del producto vive aquí. **Hay que extraer primero `OrganizationRepository`** y solo entonces se puede tratar el RAG legacy como prescindible.

### 3.3 Diagnóstico

- **Imports:** el motor Autopilot (`triage/actions/certify/defects/ai`) **no importa** el RAG legacy. A nivel de módulo el aislamiento es bueno.
- **Runtime/entrypoint:** **mal aislado.** El legacy es el host del proceso, se carga en el boot, y cuelga endpoints sin auth. El Autopilot debería ser la app principal (`api_v2.py` ya define el `router`); la app legacy debería desmontarse o, al menos, dejar de ser el entrypoint y de cargar RAGAS en el arranque.
- **Deuda muerta cuantificada:** ~390 líneas claramente muertas (`vector_store`+`loader`+`model`+`retriever`+`prompts`+`inspector`+`history`) eliminables tras quitar `api.py`/`main.py`; +95 (`structured_analyzer`) y +121 (`evaluator`) tras retirar `/analyze` y `/evaluate` legacy.

**Fix (M):** (1) crear `app.py`/`asgi.py` que monte **solo** `v2_router` y ponerlo como `CMD` del Dockerfile; (2) extraer `OrganizationRepository` de `tenant_kb`; (3) decidir el futuro de `/v2/analyze` (¿se mantiene el RAG o se jubila?); (4) `git rm` de los módulos muertos + `api.py`/`main.py`. Hacerlo **antes de la demo** elimina superficie sin auth y peso de arranque.

---

## 4. Patrones

### 4.1 Repository pattern — correcto, pero con duplicación de plomería

Cinco repos implementan el patrón con membership-gating en la capa de app (correcto, porque el pooler hace BYPASS de RLS — documentado en `defects/repository.py:29-35`). El problema es la **plomería repetida**:
- `def _connect` **×5**: `tenant_kb:51`, `certify/repository:19`, `defects/repository:42`, `jira/integrations_repository:20`, `actions/repository:19`.
- `_set_claims` **×4** + `_set_user_claims` **×1** (`tenant_kb:56`): **inconsistencia de nombre** y, además, `defects/repository._connect` hace `register_vector` mientras que `actions/repository._connect` no (correcto, pero divergente y no documentado el porqué).
- Guard de membership inline (`select exists(... memberships ...)`) **×36**.

**Fix (S-M):** `src/db.py` con `BaseRepository` (`_connect`, `_set_claims`, helper `_require_member`). Reduce ~36 repeticiones a 1 y elimina la divergencia `register_vector`/nombres.

### 4.2 Inmutabilidad — **respetada**

El barrido de mutaciones (`.append/.update/.extend`) solo encuentra **acumuladores locales** que construyen objetos nuevos (`out.append`, `ctx.append`, `proposals.append`, `counts[k]=`…). `root_cause.py:99-104` es ejemplar: documenta "retorno inmutable (no muta out en el lugar)" y devuelve `{**out, ...}`. No se detecta mutación de parámetros ni de estructuras compartidas en el motor Autopilot. (Lo único mutable-de-arranque son los 16 singletons globales de `api_v2.py`, que es un patrón de cache de DI aceptable, no mutación de datos.)

### 4.3 Manejo de errores y degradación — **el punto más fuerte y consistente**

- **API:** cada endpoint mapea excepciones a HTTP de forma uniforme (`ValueError→400/422`, `PermissionError→403`, `psycopg.Error→502`, `SigningKeyMissing/GitHubAuthError→503`). Consistente en los 33 endpoints.
- **Degradación IA homogénea:** el LLM nunca tumba el servicio. `generate_structured` degrada con `on_failure` (`generate.py:33-49`); `api_v2` envuelve `get_llm_provider()` en `try/except → provider=None` (líneas 936-939, 964-967) y los singletons LLM se construyen perezosos con wrappers `_LazyRootCauseAnalyzer`/`_LazySelfHealExplainer` (231-246) precisamente para que "mala config del LLM degrade en vez de tumbar el servicio". `ai_repair.py:58` y `nl_query`/`briefing` "nunca lanzan". Esto es coherente con el principio "determinismo donde firmo, IA donde multiplico".
- **Los `except Exception` están justificados y comentados** (`# noqa: BLE001` con razón). El único con riesgo operativo es `ci_webhook` (`api_v2.py:513`): el triaje inline degrada con `logger.exception` pero **sin marcar `triage_status` ni alertar** → un run sin veredictos queda invisible (ya recogido como M4 en la auditoría previa).

### 4.4 Constantes mágicas y duplicación de dominio

- **`_CATEGORIES` ×5 con órdenes/contenidos distintos:** `certify/certificate.py:3` y `certify/gate.py:6` (`real,flaky,maintenance,infra,unknown`); `triage/service.py:10` (`flaky,infra,maintenance,real,unknown` — **orden distinto**); `triage/engine.py:6` `_HUMAN_CATEGORIES` (4 sin `unknown`); `actions/service.py:8` (otro dominio: `quarantine,ticket,self_heal`); y el set **hardcodeado inline** en `defects/repository.py:837`. Riesgo de divergencia silenciosa al añadir una categoría.
  **Fix (S):** `src/domain/constants.py` con `HUMAN_CATEGORIES`/`TRIAGE_CATEGORIES`/`ACTION_KINDS`.
- **Números mágicos de truncado dispersos** (la lista que el prompt anticipaba):
  - `ai/generate.py:11` — `_build_context_block` corta a **`[:10]`** snippets (≡ duplicado exacto en el legacy `structured_analyzer.py:42`). Sin constante ni razón documentada; puede tirar evidencia citable silenciosamente.
  - `api_v2.py:735` root-cause `[:8000]`; `root_cause.py:6` `_MAX_FAILURES=6` y `:300`; `assurance/verdict.py:17` `[:5]`; `briefing.py:56` `[:5]`; `nl_query.py:6` `_MAX_FALLBACK=5`; `triage/patterns.py:30` `[:50000]`; `defects/fingerprint.py:43` `[:200]`; `tiebreaker.py:62` `[:1000]`. Los del Bloque B (`_MAX_*`) sí están nombrados; los `[:N]` crudos no.
  **Fix (S):** nombrar los `[:N]` como constantes de módulo (`_MAX_CONTEXT_SNIPPETS=10`, etc.).
- **`_ACTION_STATUSES`** (`api_v2.py:91`) duplica el dominio de estados que también vive en SQL/`actions/repository`. Menor.

### 4.5 Fronteras de capa — **limpias**

- Ningún módulo de dominio importa `api_v2` ni `fastapi` (única excepción correcta: `security.py`, el adaptador de auth). **Sin fugas de capa.**
- El acoplamiento a `AssuranceRepository` se hace por **inyección por constructor** en servicios (`certify/service.py:13`, `gate.py:29`, `ci/ingestion_service.py:16`, `jira/ingestion_service.py:17`) y por `Depends` en la API — DI correcta, no acoplamiento rígido.
- **Sin dependencias circulares** detectadas.
- Los `__init__.py` de los 10 paquetes están **vacíos (0 líneas)**: las fronteras públicas son por convención, no declaradas. Menor, pero declarar `__all__`/re-exports ayudaría a fijar la API de cada paquete a medida que crece.

---

## 5. `src/ai/` (Bloque B) — **bien factorizado, sin duplicación**

Respuesta directa a la pregunta del encargo: **`generate_structured` SÍ es una base sólida reusada, no hay duplicación.**

`ai/generate.py::generate_structured` (55 líneas) concentra: construcción del prompt+contexto, llamada al provider, parseo tolerante de JSON (`_parse_json` extrae el primer `{...}`), relleno con defaults del schema y **degradación parametrizada** (`on_failure="fallback"|"none"`). Los cinco consumidores delegan en él sin reimplementar nada:

| Consumidor | Reusa `generate_structured` | Capa propia |
|------------|:---------------------------:|-------------|
| `ai/judge.py` | sí (`on_failure="none"`) | `_clamp` 0-1 de scores |
| `ai/nl_query.py` | sí | fallback a listado de familias |
| `ai/briefing.py` | sí | `_fallback_briefing` determinista + `build_run_data` (agregación citable) |
| `assurance/root_cause.py` | sí | prompt/contexto puros + normalización inmutable |
| `actions/ai_repair.py` | sí | validación "old_block ∈ source" + `_MIN_CONFIDENCE=0.5` |

Patrón uniforme en todos: **schema-como-dict de defaults**, **citas (`citations`) obligatorias**, y prompt que marca el contexto como "datos NO confiables, nunca instrucciones" (defensa anti prompt-injection — consistente en judge/nl_query/briefing/root_cause/ai_repair). Cada uno es pequeño (36-82 líneas) y testeable. **Es el subsistema mejor diseñado del repo.**

Únicas pegas, menores: (1) el `[:10]` de `_build_context_block` (§4.4) afecta a **todos** los consumidores a la vez sin que ninguno lo sepa; (2) `_BRIEFING_SCHEMA`/`_REPAIR_SCHEMA` usan tuplas `()` como default de listas mientras otros usan `[]` — cosmético.

---

## 6. Deuda priorizada (por impacto)

> Ordenada por impacto en **producto vendible + demo del concurso**. (S<½d · M≈1-2d · L>2d.)

### 🔴 Pagar antes de la demo / primeros clientes
1. **D-ARQ-1 — El entrypoint de prod es la app legacy y carga RAG sin auth en el boot.** `Dockerfile`+`api.py:32,42-58,60-127`. Superficie sin autenticación (`/analyze`,`/sync`,`/history`,`/evaluate`) y peso de arranque (RAGAS) innecesarios. **Fix (M):** `asgi.py` que monte solo `v2_router`; cambiar `CMD`; jubilar/securizar los endpoints legacy. **Mayor ROI: cierra un agujero de seguridad y limpia el arranque de un tiro.**

### 🟠 Pagar en la siguiente tanda de robustez
2. **D-ARQ-2 — God Repository `defects/repository.py` (988, +36).** Creció pese a estar marcado. Cada bloque nuevo lo agrava. **Fix (M, ~2d):** extraer `TriageRepository` + `CalibrationRepository`.
3. **D-ARQ-3 — Router monolítico `api_v2.py` (974, +83).** **Fix (M, ~1d):** `dependencies.py` + sub-routers por dominio.
4. **D-ARQ-4 — Plomería de repos duplicada** (`_connect` ×5, `_set_claims`/`_set_user_claims` inconsistente, guard ×36, `register_vector` divergente). **Fix (S-M):** `BaseRepository` en `src/db.py`.

### 🟡 Higiene (baratas, alto orden/seguridad de evolución)
5. **D-ARQ-5 — `_CATEGORIES` ×5 con órdenes distintos.** Riesgo de divergencia. **Fix (S):** `src/domain/constants.py`.
6. **D-ARQ-6 — Números mágicos de truncado** (`[:10]` de `_build_context_block` el más peligroso: tira evidencia citable; +`[:8000]`,`[:5]`…). **Fix (S):** constantes nombradas.
7. **D-ARQ-7 — ~390 líneas de RAG legacy muerto** (`vector_store`,`loader`,`model`,`retriever`,`prompts`,`inspector`,`history`) + `main.py`. Eliminables tras D-ARQ-1. **Fix (S):** `git rm` (tras extraer `OrganizationRepository` de `tenant_kb`).
8. **D-ARQ-8 — `tenant_kb.py` (505) mezcla RAG legacy + CRUD de orgs del Autopilot.** Bloquea jubilar el legacy. **Fix (M):** extraer `OrganizationRepository`.
9. **D-ARQ-9 — `__init__.py` vacíos** (sin API pública declarada). **Fix (S, opcional):** `__all__`/re-exports por paquete.

### Lo que YA se pagó desde la auditoría del 25-jun (señal positiva)
- **B2 (atomicidad approve→materialize):** resuelto. `actions/repository.py` ahora tiene estado `materializing` con transición condicional (`where a.status='approved'`, `mark_materializing:145`), `materialize_action` exige `status='materializing'` (137), `revert_to_approved` (163) y reclamo de zombies a los 15 min (153-154). `actions/service.py:100-140` orquesta el lazo idempotente con re-lectura ante carrera.
- **B3 (idempotencia de ingesta):** resuelto. `ingest_ci_run` usa `on conflict (org_id, run_uid) ... do nothing returning id` (`defects/repository.py:254`) con re-SELECT y `deduplicated=True`.
- **A3 (métrica del foso contaminada):** resuelto. `set_family_label` ahora deriva `engine_category = "unknown" if er["llm_assisted"] else er["category"]` (`defects/repository.py:862-864`) — mide el motor, no motor+LLM.

Que tres bloqueantes/altos previos estén pagados (con `for update`, `on conflict`, re-lectura ante carrera) indica un equipo que **sí amortiza la deuda señalada**. La excepción son M1/M2 (los God-objects), que no solo no se pagaron sino que crecieron — de ahí su prioridad aquí.

---

## 7. Lo que está sorprendentemente bien

- **El Bloque B (`src/ai/`)**: base reusada de verdad, cero duplicación, degradación uniforme, defensa anti-injection consistente. Es el mejor subsistema del repo (§5).
- **Degradación IA disciplinada en todo el stack**: el LLM jamás tumba un endpoint; wrappers Lazy + `provider=None` en todas partes (§4.3). Coherente con el principio rector del proyecto.
- **Inmutabilidad**: respetada sin fisuras en el motor; incluso comentada explícitamente donde importa (`root_cause.py:94`).
- **Fronteras de capa**: ningún dominio importa FastAPI ni la API; acoplamiento solo por DI; sin ciclos (§4.5).
- **Disciplina de pago de deuda**: B2/B3/A3 cerrados con las técnicas correctas (`for update`, `on conflict`, re-lectura).
- **Granularidad general**: media de ~75 líneas/archivo; `ingest/`, `triage/`, `actions/selfheal/` son ejemplares en "muchos archivos pequeños".

**Conclusión:** la base **aguanta crecer hacia producto vendible y soporta la demo**, siempre que se corte primero el entrypoint legacy (D-ARQ-1) y se planifique partir los dos God-objects antes de que el próximo bloque los empuje más allá de mantenibilidad. La arquitectura del *motor* es sólida; la deuda está **localizada y es predecible** (deuda de proyecto por fases), no estructural.
