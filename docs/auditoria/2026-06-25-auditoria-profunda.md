# Auditoría profunda — Mnemo Autopilot (2026-06-25)

Auditoría de todo el proyecto tras mergear F1–F5 (main `d82f54a`). Seis dimensiones en paralelo: seguridad, correctitud, arquitectura, BD/rendimiento, tests, producto. Hallazgos agrupados por severidad y tema (no por dimensión), con ubicación, impacto, fix y esfuerzo (S<½d · M≈1-2d · L>2d).

## Veredicto

**Base sólida con deuda concreta.** El núcleo determinista (triaje R0–R6, certificado, firma Ed25519, gate) es correcto y está bien probado; el aislamiento multitenant por-org está implementado sin fisuras (membership en cada repo); cripto bien usada; frontend limpio. **Pero** hay 3 bloqueantes antes de exponer a clientes/concurso, y la **demo de 3 actos no es ejecutable e2e hoy**. Arquitectura: B+ (deuda predecible de proyecto por fases). Tests: amplios (496) pero sin E2E, sin coverage gate, y la integración corre contra **prod sin rollback**.

---

## 🔴 Bloqueantes (Critical)

### B1 — RLS sin `force` en las 7 tablas base (incl. `memberships`)
`db/migrations/001_multitenant_kb.sql` crea `profiles, organizations, memberships, documents, chunks, embeddings, analyses` con `enable` pero **nunca `force row level security`** (`analyses` además sin confirmar el `enable`). Es exactamente el invariante que se violó en 005 y se parcheó en 013 — pero sobre las tablas más críticas (`memberships` define toda la autorización) y desde el día 1. Sin `force`, las policies no aplican al owner de la tabla; si el rol de la app es owner, el aislamiento RLS (defensa frente a PostgREST/anon key) **no existe**.
**Fix (S):** migración `016` con `force` en las 7 tablas. Adoptar como gate de release: `select relname, relrowsecurity, relforcerowsecurity from pg_class where relnamespace='public'::regnamespace and relkind='r';` (debe dar `t,t` en todas). Esta query habría cazado 005 y B1.

### B2 — `approve → materialize` no es atómico (artefacto huérfano / Issue·PR duplicado)
`src/actions/service.py:93-106` + `src/actions/repository.py:115-128`. Son 3 transacciones: approve (DB) → crear Issue/PR (GitHub) → materialize (DB). Si el proceso muere entre crear el artefacto y `materialize_action`, la acción queda `approved` zombie y se pierde el `artifact_ref` (solo vive en memoria). El reintento re-entra por la rama `approved` y vuelve a materializar → **duplicado**, evitado SOLO por el marcador idempotente best-effort que **degrada a crear-igualmente si el search de GitHub falla**. H4 (correctitud): dos `approve` concurrentes pueden materializar ambos. Para un producto que promete "Nivel 2: nada externo sin approve, nunca duplica", la garantía no se sostiene.
**Fix (M):** estado intermedio `materializing` + `SELECT … FOR UPDATE` (transición `approved→materializing` con `where status='approved'`, quien pierde el rowcount no materializa); persistir `artifact_ref` antes del commit final; marcador como reconciliación, no como mecanismo primario.

### B3 — Idempotencia de ingesta falla bajo concurrencia (502 espurio)
`src/defects/repository.py:250-274` + `src/api_v2.py:478-479`. `ingest_ci_run` deduplica con check-then-insert (SELECT por `(org_id, run_uid)`, luego INSERT) **sin `ON CONFLICT`**, pese a existir el índice único parcial. Dos entregas concurrentes del mismo `run_uid` (reintento de GitHub Actions) pasan ambas el SELECT → el 2º INSERT viola el índice → `UniqueViolation` → **HTTP 502**. La idempotencia falla justo en el caso que debía cubrir; CI reintenta → cascada.
**Fix (S):** `INSERT … ON CONFLICT (org_id, run_uid) WHERE run_uid IS NOT NULL DO NOTHING RETURNING id`; si no devuelve fila, re-SELECT y `deduplicated=True`.

---

## 🟠 Altos

### Seguridad
- **A1 — Falta authz por ROL.** `src/jira/integrations_repository.py`, `src/actions/repository.py:99,115`. El esquema tiene `owner/admin/member/viewer` + `is_org_admin()`, pero la app **solo** comprueba `is_org_member`. Un `member` puede reconfigurar `repo_full_name`/`installation_id` (→ **redirigir los PRs/credenciales del org a un repo que controle**) y approve/materialize acciones (diluye el gate Nivel 2). **Fix (M):** check `role in ('owner','admin')` en `upsert_*_config` y `approve/materialize/reject_action`.
- **A2 — `repo_full_name`/`file_path` sin validar en URLs de GitHub.** `src/ci/github_app.py` (múltiples). Vienen del cliente sin validador (`GitHubConfigRequest`) y se interpolan crudos en rutas y en la query de búsqueda. **Fix (S):** validador Pydantic `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`; `urllib.parse.quote(file_path, safe="/")`; verificar que el repo pertenece a la installation.

### Correctitud
- **A3 — Métrica del foso contaminada.** `src/defects/repository.py:845-852`. `set_family_label` toma `engine_category` del último `triage_verdict`, pero si fue resuelto por el LLM, `tv.category` ya es la decisión del LLM (no del motor R6/unknown). La precisión (`get_calibration_metrics`) mide "motor+LLM", no "motor" → **sesga al alza el dato que vende el diferenciador**. **Fix (S):** guardar la categoría original del motor (o `rule_applied`/flag de ambigüedad) y medir contra esa.
- **A4 — Familia duplicada si firma exacta existe con `centroid` NULL.** `src/defects/repository.py:72-88`. `_query_candidates` filtra `centroid is not null` en ambas ramas; una familia con firma exacta pero centroide nulo queda invisible → se crea otra con la misma `signature` → `UniqueViolation` que **revienta la ingesta entera** (rollback del run). **Fix (S):** la rama de firma exacta no debe exigir `centroid is not null`.
- **A5 — `save_actions` delete+insert no idempotente.** `src/actions/repository.py:52-53`. Sin `unique(triage_verdict_id)`; una re-propuesta concurrente o tras un approve puede crear 2 acciones para el mismo veredicto. **Fix (S):** `unique(triage_verdict_id)` (parcial sobre estados vivos) o `ON CONFLICT DO UPDATE`.

### Rendimiento / BD
- **A6 — Índices FK faltantes en hot paths.** `triage_verdicts.failure_id` (009), `actions.triage_verdict_id` (010), `triage_corrections.family_id` (015), `test_runs(org_id,project,commit_sha)` (007, para `intermittent_same_sha`), `certificates.org_id` (014). **Fix (S):** migración `016` con los 5 índices (parcial donde aplique).
- **A7 — N+1 inserts gratuitos.** `record_test_results`, `save_dom_snapshots`, `save_triage_verdicts`, `save_actions` (defects/repository.py) y chunks+embeddings (`tenant_kb.py:226`) insertan fila a fila. ~190 round trips extra por ingest de tamaño medio (~570 ms a Supabase remoto). **Fix (S-M):** `executemany`/multi-row VALUES; CTE `INSERT…RETURNING` para chunks+embeddings.
- **A8 — `is_org_member` llama `auth.uid()` por-fila.** `001:120`. La policy no puede hoist la llamada. **Fix (S):** envolver como `(select auth.uid())` dentro de la función. (Relevante si se activa RLS real tras B1.)
- **A9 — IVFFlat sobre columna nullable.** `failures.embedding` (002) y `defect_families.centroid` (003) — el índice incluye NULLs. **Fix (S):** índice parcial `where embedding/centroid is not null` o `NOT NULL`. Plan: HNSW cuando se superen ~50k filas (lists=100 degrada).

---

## 🟡 Medios

### Arquitectura (deuda, refactors mecánicos)
- **M1 — `AssuranceRepository` (952 líneas) God Repository** (ingesta+familias+triaje+calibración+self-heal). **Fix (M, ~2d):** extraer `TriageRepository` (líneas 626-820) y `CalibrationRepository` (822-885); ingesta/familias quedan. Mecánico (métodos auto-contenidos).
- **M2 — `api_v2.py` (891 líneas) router monolítico.** **Fix (M, ~1d):** dividir en sub-routers por dominio (`org/ingest/triage/actions/cert/ci/jira`) + `dependencies.py`; mover `_github_codehost_factory` a `src/actions`/`src/ci`. `api_v2` queda como agregador.
- **M3 — Duplicación.** `_CATEGORIES` ×4 (cert/gate/triage/engine, con órdenes distintos), `_connect`/`_set_claims` ×5, membership guard inline ×9, `reales_novel/pendientes` recomputados en `build_certificate` (riesgo de divergencia con `compute_verdict`). **Fix (S-M):** `src/db.py` (`BaseRepository`/`make_connection`) + `src/domain/constants.py`; `build_certificate` reusa `compute_verdict`.
- **M4 — Inconsistencias menores.** `_set_user_claims` vs `_set_claims` (y el primero omite `register_vector`); `get_narrator`/`get_root_cause_analyzer` sin guard `multi_tenant_enabled`; GitHub config sin `validate_*` análogo al de Jira; `ci_webhook` ejecuta triaje inline con `except Exception` silencioso (sin `triage_status`/alerta → run sin veredictos invisible). **Fix (S c/u).**

### Tests
- **M5 — Sin E2E del pipeline** (ingesta→triaje→acción→cert→gate). El flujo de la demo no está cubierto. **Fix (M).**
- **M6 — Integración corre contra PROD sin rollback transaccional** (66 tests; cleanup por `DELETE` cascade frágil; una excepción mid-setup deja basura permanente en prod; `test_evaluation.py` sin teardown visible). **Fix (M):** envolver en `BEGIN/ROLLBACK` o usar BD de test dedicada.
- **M7 — Gaps de aserción confirmados:** `triage_corrections` nunca se SELECT-verifica (`reason`/`corrected_by`/`source` — column swap invisible); `/v2/calibration` y `PATCH /v2/defects/{id}/label` sin test 502; frontend `ActionsPanel` reject + `FamilyLabelControl` error sin test. **Fix (S).**
- **M8 — Tests débiles:** `test_redos.py` (3 tests sin `assert`), `test_ci_ingestion_service` (solo "fue llamado"), aserciones con `or` compuesto. **Sin coverage tooling/threshold.** **Fix (S-M).**
- **M9 — Módulos sin tests:** `explainer.py`; y legacy `inspector/retriever/vector_store/structured_analyzer/prompts/tenant_kb` — **confirmar si son dead code** antes de acumular deuda. **Fix (S):** auditar uso y borrar lo muerto.

### Limpieza / secretos
- **M10 — `history.db` versionado** (datos de análisis). **Fix (S):** `git rm --cached history.db` + `*.db` a `.gitignore`.
- **M11 — `MNEMO_SECRET_KEY` (Fernet real) en `.env.docker`.** **Fix (S):** placeholder + doc de generación.
- **M12 — Sin rate limiting** en endpoints LLM/ingesta (`/v2/analyze`, `/v2/upload`, root-cause, ingest). **Fix (M).**

---

## 🎯 Producto / Concurso (MTP, 30-oct-2026)

Estado: **6.5/10 hoy → 8.5/10 con el top-5.** La brecha NO es técnica (el backend funciona, el frontend existe, la firma opera) sino de **demostración**: la demo de 3 actos no corre e2e hoy.

### La demo no es ejecutable e2e (máxima prioridad)
- **D1 — El reporter npm (`mnemo-playwright-reporter`) no existe como código** en el repo (solo en spec). Es el punto de entrada del Acto 2 (DOM snapshots). Para la demo: artefacto CI sintético con `dom.last_green`+`dom.failure` reales (si son null, `SelfHealActuator` devuelve None y no hay PR).
- **D2 — El seed no activa el triaje nuevo.** `scripts/seed_demo.py` siembra Allure legacy; faltan 3 artefactos pre-fabricados que activen: (a) R5 real novel → gate rojo, (b) R3 maintenance+DOM → self-heal, (c) R0/flaky calibrado → verde.
- **D3 — El gate no se publica automáticamente.** `ci_webhook` ingesta+triaja pero **no llama `publish_gate`** → rompe "push → gate rojo automático" del Acto 1. **Fix (S):** llamar `get_gate_service().publish(...)` en el webhook, degradando si GitHub no configurado.
- **D4 — `DEMO.md` describe el producto anterior**; `smoke_demo.sh` solo verifica health/login. Reescribir con el guion de 3 actos + setup de la GitHub App.
- **Momento "wow":** `verify` Ed25519 en vivo (cert válido → `{valido:true}`, modificar 1 byte → `{valido:false}`).

### Diferidos de mayor impacto
- **RAGAS / `self_eval`** del certificado (hoy `null` visible en el JSON) — Innovación (20%). El campo existe; conectar el evaluador async. (M)
- **PDF del certificado** (hoy HTML básico) — el entregable facturable, "wow" de cierre. (M)
- **Sign-offs ricos** (hoy `[]`; `actions` ya guarda `approved_by`/`approved_at`). (S-M)

### Nuevas funcionalidades de alto impacto
- Notificaciones **Slack/Teams** al proponer acción (el ciclo visible sin abrir GitHub). (M)
- **Dashboard de tendencias** (% real/flaky/mantenimiento + precisión por semana) — valor sostenido. (M)
- **Reporte ejecutivo** PDF por release (tiempo ahorrado estimado) — de herramienta a solución de negocio. (M)
- **Comparativa antes/después del foso** (precisión pre/post calibración). (S)
- **Multi-repo por org** (hoy 1 `repo_full_name`/org). (M-L)

---

## 📋 Plan de acción recomendado

**Tanda 1 — Seguridad/correctitud bloqueante (antes de cualquier cliente):** B1 (RLS force 016) · B2 (atomicidad acciones) · B3 (ON CONFLICT ingesta) · A1 (authz por rol) · A2 (validar repo_full_name). Incluir A3 (métrica foso) y A4 (familia centroid-null) — baratos y tocan el diferenciador/estabilidad.

**Tanda 2 — Robustez/rendimiento:** A6 (índices, mismo 016) · A5 (unique acciones) · A7 (executemany) · A8/A9 (RLS hoist, índices parciales) · M6 (integración fuera de prod) · M7 (gaps de aserción) · limpieza M10/M11.

**Tanda 3 — Demo del concurso (en paralelo, dueño de producto):** D1-D4 (artefactos + seed + gate auto + DEMO.md) → es lo que decide la nota. Luego RAGAS, PDF, sign-offs.

**Tanda 4 — Deuda/escala (cuando haya aire):** M1/M2/M3 (refactors), M5 (E2E), nuevas funcionalidades (Slack, dashboards), HNSW, rate limiting.

> Sugerencia transversal: añadir el chequeo de `relforcerowsecurity` y un `pip-audit`/`npm audit` como gates de CI; configurar coverage con threshold (el proyecto declara 80% pero no lo mide).
