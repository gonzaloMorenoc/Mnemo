# Mnemo — Modelo de datos y aislamiento

Referencia del esquema `public` tal como queda tras aplicar las migraciones `db/migrations/001` a `030`. La fuente de verdad son esos ficheros SQL; donde la semántica depende del código, se cita el módulo que la fija.

Convenciones del documento:

- «RLS completo» = `enable row level security` + `force row level security` + policy basada en `is_org_member(org_id)`.
- Las columnas añadidas después de la migración que crea la tabla llevan el número entre paréntesis, p. ej. `run_uid` (008).
- Todas las tablas tienen `id uuid` con `gen_random_uuid()` salvo donde se indica, y `org_id` con FK a `organizations` y `on delete cascade`.

---

## 1. Aislamiento entre tenants (IMPORTANTE)

Las migraciones declaran RLS en todas las tablas de `public`, con policies basadas en `is_org_member(org_id)` / `auth.uid()`. **Pero** el backend se conecta por el *Session pooler* de Supabase con un rol que tiene `rolbypassrls = true`: **RLS no se aplica** a las consultas de la app.

Por eso el **aislamiento real lo hacen los filtros por membership de cada repositorio**. Está documentado en `src/defects/repository.py` (docstring de `AssuranceRepository` y de `_set_claims`) y repetido en `src/actions/repository.py`, `src/knowledge/proposal_repository.py`, `src/ci/ingest_tokens.py` y `src/jira/integrations_repository.py`. El patrón:

```sql
where ... and exists (
  select 1 from public.memberships m
  where m.org_id = <tabla>.org_id and m.user_id = %s
)
```

o una comprobación previa `select exists(... memberships ...)` que corta con `[]`, `False` o `PermissionError`. Las operaciones de gestión (emitir acta de traspaso, aprobar/rechazar propuestas, tokens) exigen además `role in ('owner','admin')`.

`_set_claims` fija `request.jwt.claim.sub` y `request.jwt.claim.role` en la sesión: es andamiaje para el día en que se conecte con un rol `authenticated` real, y es lo que permite que `join_organization_by_code` (que usa `auth.uid()`) funcione por el pooler.

**RLS es la red de seguridad** frente al acceso directo por PostgREST con la anon key, no el mecanismo primario. Cubierto por tests de integración contra Supabase real: `tests/test_assurance_repository.py` (aislamiento cross-org, rechazo de no-miembro), `tests/test_rls_behavioral.py`, `tests/test_migration_016_rls.py`, `tests/test_qa_knowledge_rls.py` y `tests/test_test_assets_rls.py`.

> Defensa en profundidad: todas las queries usan parámetros (`%s`, sin concatenación) y el filtro de membership es independiente de RLS.

### Estado RLS por tabla

Todas las tablas de `public` tienen `enable` + `force` (las 7 de `001` recibieron el `force` en `016`; `org_integrations` el RLS entero en `013`). Ninguna queda sin RLS. Las que **no** usan la policy estándar `is_org_member(org_id)` lo hacen a propósito:

| Tabla | Policy | Nota |
|---|---|---|
| `profiles` | `user_id = auth.uid()` | Por usuario, no por org. |
| `organizations` | select `is_org_member(id)`; insert `created_by = auth.uid()`; update `is_org_admin(id)`; delete solo owner | |
| `memberships` | select propio o miembro; escritura `is_org_admin(org_id)` | |
| `documents`, `chunks`, `embeddings` | por `scope` (`global` / `user` / `org`) | RAG v1 legacy. |
| `analyses` | propio o miembro de la org | RAG v1 legacy. |
| `defect_families` | `scope = 'global' or is_org_member(org_id)`; escritura solo `scope = 'org'` | |
| `ingest_tokens` | select `is_org_member`; insert/update/delete `is_org_admin` (+ `created_by = auth.uid()` en insert) | Tabla de credenciales. |
| resto | `is_org_member(org_id)` para todo | |

### Grants al rol `authenticated`

Relevante solo para PostgREST (el pooler no los necesita):

- `certificates` y `triage_corrections`: solo `select, insert` (append-only a nivel de grant).
- `knowledge_proposals`: `insert, update, delete` revocados en `026`; queda `select`.
- `ingest_tokens`: sin grants (evita exponer `token_hash`).
- `qa_knowledge`, `test_assets`, `handover_acts`, `org_integrations`: las migraciones no conceden grants.
- Resto: `select, insert, update, delete`.

### Funciones

| Función | Qué hace |
|---|---|
| `is_org_member(org)` | `exists` en `memberships` con `user_id = (select auth.uid())`. Reescrita en `016` con subconsulta para que el planner evalúe `auth.uid()` una vez y no por fila. |
| `is_org_admin(org)` | Igual, con `role in ('owner','admin')`. |
| `join_organization_by_code(code)` | `security definer`: busca la org por `join_code` (sin distinguir mayúsculas) e inserta la membership `member`. |
| `create_owner_membership()` | Trigger `after insert` en `organizations`: crea la membership `owner` del creador. |
| `set_default_org_owner_membership()` | Trigger `before insert` en `organizations`: **genera el `join_code`** (10 hex) si viene nulo. El nombre es engañoso. |
| `search_chunks_scoped(vec, n)` | Búsqueda del RAG v1 legacy; no la usa el API v2. |

---

## 2. Vectores `vector(384)`

Modelo por defecto: `paraphrase-multilingual-MiniLM-L12-v2` (`EMBEDDING_MODEL` en `src/config.py`), 384 dimensiones. Si se cambia de modelo, los vectores viejos y nuevos no son comparables: `python3 -m scripts.reembed` re-embebe todas las columnas del API v2 con la misma receta que la escritura.

| Columna | Texto embebido | Dónde se calcula | Índice |
|---|---|---|---|
| `failures.embedding` | `f"{error_type} {message}"` tras sanitizar el mensaje | `src/defects/ingestion_service.py`, `src/ci/ingestion_service.py` | `ivfflat` parcial (`embedding is not null`) |
| `failures.embedding` (fallos importados de Jira) | `f"{summary} {description}"` del bug | `src/jira/ingestion_service.py` | (el mismo) |
| `defect_families.centroid` | Media de los embeddings de sus fallos: media móvil incremental en la ingesta (`src/defects/centroid.py`); `reembed` la recalcula como media exacta y deja `NULL` en familias sin fallos | `src/defects/repository.py` | `ivfflat` parcial (`centroid is not null`) |
| `qa_knowledge.embedding` | `embedding_text(title, challenge, approach)` = las partes no vacías unidas por salto de línea | `src/knowledge/repository.py` | `ivfflat` parcial |
| `test_assets.embedding` | `asset_descriptor(path, content)`: ruta + títulos de tests (`test(…)`, `it(…)`, `describe(…)`, `Scenario(…)`, `def test_…`) + comentarios, tope 8000 caracteres. Sin títulos reconocibles (helpers, page objects), el contenido tal cual | `src/repo_ingest/descriptor.py` | `ivfflat` parcial |
| `triage_corrections.reason_embedding` (030) | La `reason` del etiquetador (solo filas con razón) | `src/api_v2.py` (`_embed_reason`), `scripts/reembed.py` | Ninguno, a propósito |
| `embeddings.embedding` | Chunks del RAG v1 legacy | fuera del API v2 | `ivfflat` |

Notas:

- Todos los `ivfflat` usan `vector_cosine_ops` con `lists = 100`. Los de `failures` y `defect_families` pasaron a parciales en `016`.
- `reason_embedding` no lleva índice porque la búsqueda de familias ordena por la media de dos distancias — `(centroid <=> q + reason_embedding <=> q) / 2` sobre la corrección con razón más reciente, o solo el centroide si no hay — y ningún índice vectorial sirve esa expresión; el volumen por org es de decenas de familias.
- Las filas con `reason_embedding` a `NULL` se buscan solo por centroide hasta que `reembed` las rellena.

---

## 3. Tablas

### 3.1 Tenancy (001)

| Tabla | Propósito | Columnas clave |
|---|---|---|
| `organizations` | Org / cliente | `name`, `created_by` (FK `auth.users`, `on delete restrict`), `join_code` unique, `created_at` |
| `memberships` | **Fuente de verdad del aislamiento** | PK `(org_id, user_id)`, `role` enum `org_role` ∈ `owner`/`admin`/`member`/`viewer` |
| `profiles` | Perfil por usuario (legacy) | PK `user_id`, `display_name`, `default_org_id` (FK, `set null`). El código actual no la usa. |

### 3.2 RAG v1 legacy (001)

`documents`, `chunks`, `embeddings` (con `scope` enum `kb_scope` ∈ `global`/`user`/`org` y CHECKs que atan `scope` a `owner_user_id`/`org_id`; `global` exige `sanitized_content` en `chunks`) y `analyses` (`bigserial`). Pertenecen al RAG v1, que está fuera del arranque de producción (`asgi.py` monta solo el API v2). El código del API v2 y `scripts/reembed.py` no las tocan.

### 3.3 Ingesta y Defect DNA (002, 007)

**`test_runs`** — un run de CI o un reporte subido.

| Columna | Detalle |
|---|---|
| `project` | `text not null`; el «proyecto» es solo este texto, no hay tabla de proyectos |
| `source` | CHECK ∈ `allure`, `junit`, `testng`, `cucumber`, `playwright`, `cypress`, `robot`, `jira` (última versión en `005`) |
| `commit_sha` (007) | Ata el run a un commit (señal flaky mismo-SHA) |
| `run_uid` (008) | Idempotencia: índice único parcial `(org_id, run_uid) where run_uid is not null`. El webhook CI usa el UUID que genera el reporter; la subida de reportes deriva `report:{project}:{sha256 del fichero}` |
| `summary` | `jsonb` `{ingested, known, novel, manifest?}`; el `manifest` (manifiesto de ejecución) lo lee el acta |
| `ci_ref` | Sin uso en el código actual |

**`failures`** — un fallo dentro de un run.

| Columna | Detalle |
|---|---|
| `run_id` | FK `test_runs`, cascade; índice `idx_failures_run_id` (025) |
| `test_name`, `error_type`, `message`, `trace` | `message` y `trace` se guardan sanitizados |
| `fingerprint` | Firma determinista; coincide con `defect_families.signature` |
| `embedding` | Ver §2 |
| `sanitized` | La ingesta actual siempre escribe `true` |
| `defect_family_id` | FK `defect_families`, `on delete set null` |
| `external_ref`, `external_url` (005) | Bug de Jira de origen; índice de dedup `(org_id, external_ref)` parcial (006) |
| `file`, `line` (012) | Ubicación del test para el self-heal |

**`defect_families`** — agrupación de fallos («Defect DNA»: `failures` agrupados por familia a través de proyectos y tiempo).

| Columna | Detalle |
|---|---|
| `scope` | CHECK ∈ `org`/`global`; `defect_families_scope_chk`: `org` exige `org_id`, `global` exige `org_id` nulo. El código solo crea `org` |
| `signature` | Índice único parcial `(org_id, signature) where scope = 'org'` (003): red de seguridad contra familias duplicadas |
| `title` | Al crear: `error_type`, o los 80 primeros caracteres del mensaje |
| `root_cause` | Lo escribe el análisis de causa raíz |
| `status` | CHECK ∈ `open`/`resolved`, default `open`; ningún código la cambia |
| `label` (009) | CHECK ∈ `flaky`/`real`/`maintenance`/`infra`/`unknown`, **`not null default 'unknown'`** (ver §4) |
| `occurrence_count`, `centroid`, `first_seen`, `last_seen` | Se actualizan en cada fallo que casa |

**`test_results`** (007) — resultado por test y run, incluidos los `pass` (base de la señal de intermitencia). `status` CHECK ∈ `pass`/`fail`/`flaky`/`skipped`; `retried bool`.

**`dom_snapshots`** (007) — DOM por test para el self-heal. `project`, `test_name`, `kind` CHECK ∈ `last_green`/`failure`, `content`, `commit_sha`. Índice `(org_id, project, test_name, kind)`.

### 3.4 Triaje, acciones y lazo de aprendizaje (009, 010, 015)

**`triage_verdicts`** — veredicto del motor por fallo.

| Columna | Detalle |
|---|---|
| `failure_id`, `run_id` | FK, cascade |
| `category` | CHECK ∈ `flaky`/`infra`/`maintenance`/`real`/`unknown` |
| `confidence` | `double precision` |
| `rule_applied` | Regla del motor (`R0_calibrated`, `R0_prior_contradicted`, `R5_real_novel`…) |
| `evidence_bundle` | `jsonb` |
| `requires_approval`, `llm_assisted` | `bool` |
| `status` | CHECK ∈ `resolved`/`needs_tiebreak` |

**`actions`** — acción propuesta sobre un veredicto (Nivel 2).

| Columna | Detalle |
|---|---|
| `triage_verdict_id`, `run_id` | FK, cascade |
| `kind` | CHECK ∈ `quarantine`/`ticket`/`self_heal` |
| `status` | CHECK ∈ `proposed`/`approved`/`rejected`/`materializing`/`materialized` (017). `materializing` serializa `approved → materializing → materialized` para evitar la doble materialización |
| `payload`, `summary`, `artifact_ref`, `reject_reason` | |
| `approved_by` | FK `auth.users`, `set null` (011); `approved_at`, `materializing_at` (017) |

**`triage_corrections`** (015) — historia auditable motor vs. humano.

| Columna | Detalle |
|---|---|
| `family_id` | FK `defect_families`, cascade |
| `engine_category` | Predicción independiente del motor: último veredicto de la familia **excluyendo** las reglas `R0*` (que son eco de la etiqueta humana); `unknown` si fue asistido por LLM; `NULL` si no hay |
| `human_category` | La etiqueta puesta |
| `source` | `text not null default 'family_label'`, **sin CHECK**. El código escribe `family_label` o `conflict_review` (este último cuando el último veredicto de la familia es `R0_prior_contradicted`) |
| `reason` | Texto libre del etiquetador |
| `reason_embedding` (030) | Ver §2 |
| `corrected_by`, `corrected_at` | |

### 3.5 Actas firmadas (014, 028, 029)

**`certificates`** — acta de release, firmada Ed25519.

| Columna | Detalle |
|---|---|
| `run_id` | **`not null`**, FK `test_runs`, cascade. Puede haber varias por run; se usa la más reciente (índice `(run_id, created_at desc)`) |
| `canonical_json` | Payload firmado, `schema: "mnemo.cert.v3"` (`src/certify/certificate.py`): `attestation_type`, `disclaimer`, `execution_manifest`, `identity` (org, proyecto, commit, run, `created_at`, versiones, `algorithm: "ed25519"`, `key_id`), `verdict`, `risk_score`, `breakdown`, `evidence`, `sign_offs`, `self_eval` |
| `signature` | Firma del JSON canónico |
| `verdict` | CHECK ∈ `apto`/`apto-con-reservas`/`no-apto`/`sin_confirmar` (029). `sin_confirmar` = run limpio sin manifiesto de ejecución completo |
| `risk_score` | `int not null` (0–100) |
| `sign_offs`, `mnemo_version`, `model_version` | |

**`handover_acts`** (028) — acta de traspaso de conocimiento de un proyecto.

| Columna | Detalle |
|---|---|
| `project` | `text not null` |
| `canonical_json` | Payload firmado, `schema: "mnemo.traspaso.v1"` (`src/continuity/service.py`): `org_id`, `project`, `created_at`, `emitted_by`, `continuity {score, dimensions}`, `inventario`, `mnemo_version`, `key_id` |
| `signature` | Misma cadena de firma y la misma puerta pública de verificación que el acta de release; lo que las distingue es `schema` |
| `score` | **Nullable**: «sin datos suficientes» se firma igual en vez de inventar un cero |
| `created_by` | Solo owner/admin pueden emitir |

Índice `(org_id, project, created_at desc)`.

### 3.6 Conocimiento (018, 020, 022, 023, 026, 027)

**`qa_knowledge`** — memoria del equipo de QA (RAG).

| Columna | Detalle |
|---|---|
| `kind` | CHECK (027) ∈ `regla_negocio`, `flujo`, `riesgo`, `glosario`, `leccion`, `reto`, `patron` (producto y fallos) + `runbook`, `dato_prueba`, `contacto`, `decision` (oficio del proyecto). La misma lista vive en `_KINDS` de `src/knowledge/repository.py` |
| `title`, `challenge`, `approach`, `outcome`, `domain`, `tags text[]`, `project` | |
| `source` | `text not null default 'manual'`, sin CHECK. Valores que escribe el código: `manual` (alta directa) y, al aprobar una propuesta, el `source` de la propuesta (`auto_triage`/`jira`/`confluence`) |
| `confidence` | CHECK ∈ `confirmado`/`inferido`. Aprobación de propuesta: `inferido` si viene del triaje, `confirmado` si es un import |
| `status` (023) | CHECK ∈ `activo`/`obsoleto`; `obsoleto` se excluye de RAG, búsqueda, grafo y huecos |
| `updated_at` (023) | Se fija en cada edición (frescura) |
| `source_url` (026) | Enlace al original (imports) |
| `defect_family_id`, `run_id` | FK nullable, `on delete set null` |
| `created_by` | `uuid not null`, sin FK |
| `embedding` | Ver §2 |

**`knowledge_proposals`** (022, 026) — bandeja «la IA propone, el humano aprueba».

| Columna | Detalle |
|---|---|
| `defect_family_id` | FK cascade (efímera sin su familia); `unique (defect_family_id)` → una propuesta por familia. Nullable desde `026` (los imports no tienen familia; el `unique` admite varios `NULL`) |
| `source` (026) | CHECK ∈ `auto_triage`/`jira`/`confluence`, default `auto_triage` |
| `external_ref`, `external_url`, `project`, `imported_at` (026) | Único parcial `(org_id, external_ref)`: una propuesta por referencia, en cualquier estado |
| — | `knowledge_proposals_anchor_chk`: `auto_triage` exige `defect_family_id`; el resto exige `external_ref` |
| `kind` | El mismo CHECK de 11 valores que `qa_knowledge` (027); default `leccion` |
| `status` | CHECK ∈ `pending`/`approved`/`rejected`; aprobar crea la fila en `qa_knowledge` en la misma transacción |
| `approved_by`, `approved_at`, `reject_reason`, `created_by` | |

**`test_assets`** (020) — tests del repo del cliente, para el estilo few-shot de Automation y el detector de huecos.

| Columna | Detalle |
|---|---|
| `repo_full_name`, `path`, `framework`, `domain` | |
| `content` | Contenido del fichero recortado a 8000 caracteres (para el few-shot) |
| `embedding` | Del descriptor, no del contenido (ver §2) |

La reingesta de un repo borra e inserta todas sus filas (`replace_for_repo`).

### 3.7 Integraciones y credenciales (005, 011, 013, 019, 021, 024)

**`org_integrations`** — credenciales por org.

| Columna | Detalle |
|---|---|
| `provider` | CHECK ∈ `jira`/`github`/`xray`; `unique (org_id, provider)` |
| `base_url` | Host de Jira / Xray Server |
| `email`, `api_token_enc`, `jql` | Nullable desde `011`. `api_token_enc` cifrado con Fernet en la app (token de Jira, `client_secret` o token de Xray). En Xray Cloud `email` guarda el `client_id` |
| `installation_id`, `repo_full_name` (011) | GitHub App. Índice único parcial sobre `installation_id where provider = 'github'` (021): una instalación pertenece a una sola org (mitigación del confused-deputy; la verificación de propiedad está además en la API) |
| `xray_mode` (019) | CHECK ∈ `cloud`/`server` |

**`ingest_tokens`** (024) — tokens de ingesta CI por org.

| Columna | Detalle |
|---|---|
| `name` | |
| `token_hash` | `unique`; sha256 del token, que en claro se muestra una sola vez |
| `created_by` | El token actúa con la identidad de quien lo creó, así que los checks de membership del pipeline aplican tal cual |
| `last_used_at`, `revoked_at` | |

---

## 4. Invariantes que el código asume

- **«Etiquetada» = `label <> 'unknown'`.** `defect_families.label` es `not null default 'unknown'`, así que el default no es una etiqueta humana. Lo asumen el recuento de familias calibradas de las métricas del motor (`src/defects/repository.py`) y el índice de continuidad (`src/continuity/index.py`), que no cuenta como etiquetadas las familias que nadie ha triado. `set_family_label` valida el label contra los 5 valores del CHECK antes de escribir.
- **`triage_corrections` es append-only** con `source` ∈ `family_label` | `conflict_review`. Cada etiquetado inserta una fila; nunca se edita en la app. El append-only se impone con el grant (`select, insert`) y por convención: el pooler sí puede hacer `update`, y lo hacen dos scripts fuera del flujo de usuario — `scripts/reembed.py` (rellena `reason_embedding`) y `src/demo/seed.py` (ajusta `corrected_at` de la demo).
- **`certificates` es append-only** (grant `select, insert`): re-certificar crea otra fila; se lee la más reciente por run.
- **`handover_acts` es una tabla propia, separada de `certificates`.** `certificates.run_id` es `not null` y su CHECK de veredicto forma parte de la garantía del acta de release; un traspaso no tiene run ni veredicto, y debilitar esos campos para acomodarlo contaminaría ambos modelos. Comparten la cadena de firma y la verificación pública; los distingue `schema` (`mnemo.cert.v3` frente a `mnemo.traspaso.v1`).
- **Lo firmado es reproducible:** `created_at` llega del endpoint, no de `now()` dentro de la lógica firmada; el acta de traspaso lleva el desglose y los pesos completos para poder recalcular el número.
- **Dedup de familias por firma:** el matching busca primero la familia con la `signature` exacta (además del top-K por coseno) y el índice único `(org_id, signature)` de `003` impide duplicarla.
- **Idempotencia de ingesta:** un `run_uid` repetido devuelve el run existente y su `summary` en vez de duplicar fallos y `occurrence_count`.
- **Los kinds van en dos sitios:** el CHECK de `qa_knowledge` y el de `knowledge_proposals` deben llevar la misma lista que `_KINDS`; el refine del LLM escribe el kind en la propuesta.
- **Migraciones idempotentes:** `scripts/docker_init.py` re-aplica todas las migraciones en cada arranque, en orden. Por eso las recientes usan `if not exists`, `drop constraint if exists` y `drop policy if exists` antes de `create policy`.

---

## 5. Índice de migraciones

| Nº | Qué hace |
|---|---|
| 001 | Esquema multitenant base: `organizations`, `memberships`, `profiles`, RAG v1 (`documents`, `chunks`, `embeddings`, `analyses`), `is_org_member`/`is_org_admin`, triggers de owner y `join_code`, RLS `enable`. |
| 002 | Aseguramiento: `test_runs`, `defect_families`, `failures` con `vector(384)`, RLS completo. |
| 003 | Índice único `(org_id, signature)` de familias e `ivfflat` sobre `centroid`. |
| 004 | Amplía `test_runs.source` a 7 formatos de reporte. |
| 005 | Fuente `jira`, `failures.external_ref/url` y tabla `org_integrations` (sin RLS). |
| 006 | Índice de dedup `failures (org_id, external_ref)`. |
| 007 | `test_runs.commit_sha`, tablas `test_results` y `dom_snapshots`. |
| 008 | `test_runs.run_uid` + índice único parcial (idempotencia). |
| 009 | `defect_families.label` y tabla `triage_verdicts`. |
| 010 | Tabla `actions`. |
| 011 | `org_integrations` para GitHub App (`installation_id`, `repo_full_name`, columnas Jira nullable) y FK `actions.approved_by`. |
| 012 | `failures.file` / `failures.line`. |
| 013 | Hotfix: RLS completo en `org_integrations`. |
| 014 | Tabla `certificates` (append-only). |
| 015 | Tabla `triage_corrections` (append-only). |
| 016 | `force` RLS en las 7 tablas de 001, `is_org_member` con subconsulta, índices FK, `ivfflat` parciales. |
| 017 | Estado `materializing` y `materializing_at` en `actions`. |
| 018 | Tabla `qa_knowledge`. |
| 019 | Proveedor `xray` y `xray_mode` en `org_integrations`. |
| 020 | Tabla `test_assets`. |
| 021 | Índice único de `installation_id` de GitHub (una instalación, una org). |
| 022 | Tabla `knowledge_proposals`. |
| 023 | `qa_knowledge.status` (`activo`/`obsoleto`) y `updated_at`. |
| 024 | Tabla `ingest_tokens` con policies de admin. |
| 025 | Índice `failures (run_id)`. |
| 026 | Propuestas desde imports Jira/Confluence (`source`, ancla, ref externa), `qa_knowledge.source_url`, revoca escritura REST de propuestas. |
| 027 | Kinds operativos (`runbook`, `dato_prueba`, `contacto`, `decision`) en `qa_knowledge` y `knowledge_proposals`. |
| 028 | Tabla `handover_acts` (actas de traspaso). |
| 029 | Veredicto `sin_confirmar` en el CHECK de `certificates`. |
| 030 | `triage_corrections.reason_embedding vector(384)`. |

---

## 6. Conexión a Supabase

- Usar la cadena del **Session pooler** (puerto 5432): `postgresql://postgres.<ref>:<pass>@aws-X-<region>.pooler.supabase.com:5432/postgres`.
- La conexión **directa** `db.<ref>.supabase.co:5432` es **IPv6-only** en proyectos nuevos y puede dar «no route to host» desde redes sin IPv6 enrutable.
- `DATABASE_URL` va en `.env` (ignorado por git). `multi_tenant_enabled()` requiere `DATABASE_URL` y `SUPABASE_URL`; si faltan, los endpoints `/v2` responden 503.
