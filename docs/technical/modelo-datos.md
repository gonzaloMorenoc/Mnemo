# Mnemo — Modelo de datos y aislamiento

## Esquema multitenant (migración `001_multitenant_kb.sql`)

Base reutilizada del producto original:

- `organizations` (org/cliente; `created_by`, `join_code`). Un **trigger** crea automáticamente la membership `owner` del creador.
- `memberships` (`org_id`, `user_id`, `role` ∈ owner/admin/member/viewer). **Es la fuente de verdad del aislamiento.**
- `profiles`, `analyses`, y las tablas del KB original (`documents`, `chunks`, `embeddings`) con scopes `org`/`user`/`global`.

## Esquema de aseguramiento (migración `002_assurance.sql`)

| Tabla | Campos clave (estado ACTUAL, con las columnas añadidas por migraciones posteriores) |
|---|---|
| `test_runs` | `id`, `org_id`, `project`, `source` (8 valores: `allure`/`junit`/`testng`/`cucumber`/`playwright`/`cypress`/`robot` +004, `jira` +005), `ci_ref`, `commit_sha` (+007), `run_uid` (+008, idempotencia), `summary` jsonb, `created_at` |
| `defect_families` | `id`, `scope` (`org`/`global`), `org_id`, `signature`, `title`, `root_cause`, `status` (`open`/`resolved`), `label` (+009), `occurrence_count`, `centroid vector(384)`, `first_seen`, `last_seen` |
| `failures` | `id`, `run_id`, `org_id`, `test_name`, `error_type`, `message`, `trace`, `fingerprint`, `embedding vector(384)`, `sanitized`, `defect_family_id`, `external_ref`/`external_url` (+005, Jira), `file`/`line` (+012, self-heal), `created_at` |

Índices: `ivfflat (embedding vector_cosine_ops)` para el matching por coseno; índices por `org_id`, `defect_family_id`, `fingerprint`, `signature`.

**Defect DNA** = `failures` agrupados por `defect_family_id` a través de `test_runs.project` y el tiempo. El `centroid` de cada familia es la media móvil de los embeddings de sus fallos.

### Invariante de scope

`defect_families` tiene un CHECK: `scope='org'` exige `org_id` no nulo; `scope='global'` exige `org_id` nulo. En el slice actual solo se usa scope `org`; `global` (cross-cliente sanitizado) es roadmap.

## Aislamiento entre tenants (IMPORTANTE)

Las migraciones declaran **RLS** (incluido `FORCE ROW LEVEL SECURITY`) con policies basadas en `is_org_member(org_id)` / `auth.uid()`. **Pero** se verificó empíricamente que el rol del **Session pooler** de Supabase (`postgres`) tiene `rolbypassrls = true` → **RLS no se aplica** a través de la conexión directa de la app.

Por tanto, el **aislamiento real se hace en la capa de aplicación**: cada método de `AssuranceRepository` filtra por membership explícitamente, p.ej.:

```sql
where ... and exists (
  select 1 from public.memberships m
  where m.org_id = <tabla>.org_id and m.user_id = %s
)
```

y `ingest_run` lanza `PermissionError` si el usuario no es miembro. Esto está **cubierto por tests de integración** contra el Supabase real: `tests/test_assurance_repository.py` (aislamiento cross-org, rechazo de no-miembro, agrupación cross-proyecto) más las suites conductuales de RLS `tests/test_rls_behavioral.py`, `tests/test_migration_016_rls.py`, `tests/test_qa_knowledge_rls.py` y `tests/test_test_assets_rls.py`. Estas suites sustituyen al antiguo checklist manual de validación RLS.

`FORCE RLS` queda como **red de seguridad** para el futuro (si se conecta vía un rol `authenticated` real / PostgREST en vez del rol pooler con BYPASS).

> **Defensa en profundidad:** todas las queries usan parámetros (`%s`, sin concatenación) → sin inyección SQL; y el filtro de membership es independiente de RLS.

## Conexión a Supabase

- Usar la cadena del **Session pooler** (puerto 5432): `postgresql://postgres.<ref>:<pass>@aws-X-<region>.pooler.supabase.com:5432/postgres`.
- La conexión **directa** `db.<ref>.supabase.co:5432` es **IPv6-only** en proyectos nuevos y puede dar "no route to host" desde redes sin IPv6 enrutable.
- `DATABASE_URL` va en `.env` (gitignored). `multi_tenant_enabled()` requiere `DATABASE_URL` y `SUPABASE_URL`; si faltan, los endpoints `/v2` responden 503.

---

## Migraciones (003–021)

### 003 — invariantes del matching

Índice único parcial `uq_defect_families_org_signature` sobre `(org_id, signature)` — la invariante anti-familia-duplicada del matching — e `ivfflat` sobre `defect_families.centroid`.

### 004 / 005 / 006 — más fuentes + Jira

`004` amplía `test_runs.source` a 7 formatos de report; `005` añade `jira` como fuente y `external_ref`/`external_url` a `failures` (dedup de issues); `006` añade el índice de dedup `(org_id, external_ref)`.

### 007 — `test_results` y `dom_snapshots`

Base de la señal flaky (resultado por test, incluidos los `pass`) y del self-heal (DOM verde/rojo).

| Tabla | Campos clave |
|-------|-------------|
| `test_results` | `id`, `run_id`, `org_id`, `test_name`, `status` (`pass`/`fail`/`flaky`/`skipped`), `retried bool`, `created_at` |
| `dom_snapshots` | `id`, `org_id`, `project`, `test_name`, `kind` (`last_green`/`failure`), `content text`, `commit_sha`, `created_at` |

Ambas con RLS + FORCE + policy `is_org_member(org_id)`. También añade `test_runs.commit_sha`.

### 008 — `run_uid` (idempotencia de ingesta)

`test_runs.run_uid text` + índice único **parcial** `(org_id, run_uid) where run_uid is not null`: reentregar el mismo run (retry del webhook, re-upload del mismo reporte) devuelve el run existente en vez de duplicar.

### 009 — `triage_verdicts`

Columna `label` añadida a `defect_families` (`flaky`/`real`/`maintenance`/`infra`/`unknown`, default `unknown`).

| Tabla | Campos clave |
|-------|-------------|
| `triage_verdicts` | `id`, `failure_id`, `run_id`, `org_id`, `category` (`flaky`/`infra`/`maintenance`/`real`/`unknown`), `confidence double precision`, `rule_applied text`, `evidence_bundle jsonb`, `requires_approval bool`, `llm_assisted bool`, `status` (`resolved`/`needs_tiebreak`), `created_at` |

RLS habilitado + FORCE + policy `is_org_member(org_id)`.

### 010 — `actions`

| Tabla | Campos clave |
|-------|-------------|
| `actions` | `id`, `triage_verdict_id`, `run_id`, `org_id`, `kind` (`quarantine`/`ticket`/`self_heal`), `payload jsonb`, `summary text`, `status` (`proposed`/`approved`/`rejected`/`materialized`), `artifact_ref text`, `approved_by uuid`, `approved_at`, `reject_reason text`, `created_at` |

RLS habilitado + FORCE + policy `is_org_member(org_id)`.

### 011 — `org_integrations` — soporte GitHub App

Añade `provider='github'` al constraint, columnas `installation_id`/`repo_full_name`, pasa `email`/`api_token_enc`/`jql` a nullable (solo aplican a Jira) y añade la FK `actions.approved_by → auth.users`.

### 012 — `failures.file` / `failures.line`

Ubicación del fallo en el código del test — la base del parche de self-heal.

### 013 — `org_integrations` — hotfix RLS

La tabla `org_integrations` (creada en `005_jira_integration.sql`; columnas GitHub añadidas en `011`) almacena credenciales por org (token Jira cifrado con Fernet, base_url/email/jql, installation_id/repo_full_name de GitHub App). Se creó sin RLS — Supabase advisor la clasificó como CRITICAL. Esta migración habilita RLS + FORCE + policy `is_org_member(org_id)`. El backend no se ve afectado (accede por el Session pooler, que bypasea RLS); solo se bloquea el acceso directo no autorizado.

### 014 — `certificates`

| Tabla | Campos clave |
|-------|-------------|
| `certificates` | `id`, `run_id`, `org_id`, `canonical_json jsonb`, `signature text`, `verdict` (`apto`/`apto-con-reservas`/`no-apto`), `risk_score int`, `sign_offs jsonb`, `mnemo_version text`, `model_version text`, `created_at` |

Append-only (`grant select, insert`). RLS + FORCE + policy `is_org_member(org_id)`.

### 015 — `triage_corrections`

Historia auditable del lazo de aprendizaje (veredicto del motor vs. corrección humana).

| Tabla | Campos clave |
|-------|-------------|
| `triage_corrections` | `id`, `org_id`, `family_id`, `engine_category text`, `human_category text`, `source text` (default `family_label`), `reason text`, `corrected_by uuid`, `corrected_at` |

Append-only. RLS + FORCE + policy `is_org_member(org_id)`.

### 016 — hardening (Tanda 1)

- **FORCE RLS** en las 7 tablas base de `001` (`profiles`, `organizations`, `memberships`, `documents`, `chunks`, `embeddings`, `analyses`) que tenían `enable` pero no `force` → el owner del schema podía bypasear.
- `is_org_member` reescrita con subconsulta `(select auth.uid())` para que el planner pueda hoistear `auth.uid()` fuera del bucle por fila.
- Índices FK faltantes en hot paths: `triage_verdicts(failure_id)`, `actions(triage_verdict_id)`, `triage_corrections(family_id)`, `test_runs(org_id, project, commit_sha)`, `certificates(org_id)`.
- Índices `ivfflat` parciales (excluyen filas con `embedding IS NULL`) en `failures` y `defect_families`.

### 017 — `actions` — estado `materializing`

Añade el estado intermedio `materializing` al constraint de `actions.status` (`proposed`/`approved`/`rejected`/`materialized`/`materializing`) para serializar el ciclo `approved → materializing → materialized` y evitar doble materialización. También añade `materializing_at timestamptz`.

### 018 — `qa_knowledge`

Tabla principal de la capacidad **Knowledge** (memoria RAG del equipo QA).

| Tabla | Campos clave |
|-------|-------------|
| `qa_knowledge` | `id`, `org_id`, `kind` (`regla_negocio`/`flujo`/`riesgo`/`glosario`/`leccion`/`reto`/`patron`), `title text`, `challenge text`, `approach text`, `outcome text`, `domain text`, `tags text[]`, `project text`, `source text` (default `manual`), `confidence` (`confirmado`/`inferido`), `defect_family_id uuid` (FK nullable), `run_id uuid` (FK nullable), `created_by uuid`, `created_at`, `embedding vector(384)` |

Índices: `(org_id)`, `(org_id, domain)` parcial, `ivfflat (embedding vector_cosine_ops)` parcial. RLS + FORCE + policy `is_org_member(org_id)`. Requiere extensión `vector` (ya presente por `002`).

### 019 — `org_integrations` — soporte Xray

Añade `provider='xray'` al constraint de `org_integrations.provider` (antes solo `jira`/`github`).

Añade `xray_mode text check (xray_mode in ('cloud', 'server'))`.

Reutiliza el mismo patrón de cifrado Fernet: `api_token_enc` lleva el `client_secret` (Xray Cloud) o la API token (Xray Server); `email` lleva el `client_id` (Cloud); `base_url` lleva el host de Xray Server/DC.

### 020 — `test_assets`

Los tests del repo del cliente, indexados para el estilo few-shot de Automation y el detector de gaps.

| Tabla | Campos clave |
|-------|-------------|
| `test_assets` | `id`, `org_id`, `repo_full_name`, `path`, `framework`, `domain`, `content text`, `embedding vector(384)`, `created_at` |

Índices: `(org_id)`, `(org_id, domain)` parcial, `ivfflat` parcial. RLS + FORCE + policy `is_org_member(org_id)`.

### 021 — GitHub App: instalación única

Índice único sobre `org_integrations.installation_id`: impide que dos organizaciones reclamen la misma instalación de GitHub (mitigación del confused-deputy cross-tenant).
