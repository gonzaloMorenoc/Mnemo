# Mnemo — Modelo de datos y aislamiento

## Esquema multitenant (migración `001_multitenant_kb.sql`)

Base reutilizada del producto original:

- `organizations` (org/cliente; `created_by`, `join_code`). Un **trigger** crea automáticamente la membership `owner` del creador.
- `memberships` (`org_id`, `user_id`, `role` ∈ owner/admin/member/viewer). **Es la fuente de verdad del aislamiento.**
- `profiles`, y las tablas del KB original (`documents`, `chunks`, `embeddings`) con scopes `org`/`user`/`global`.

## Esquema de aseguramiento (migración `002_assurance.sql`)

| Tabla | Campos clave |
|---|---|
| `test_runs` | `id`, `org_id`, `project`, `source` (`allure`/`junit`), `ci_ref`, `summary` jsonb, `created_at` |
| `defect_families` | `id`, `scope` (`org`/`global`), `org_id`, `signature`, `title`, `root_cause`, `status` (`open`/`resolved`), `occurrence_count`, `centroid vector(384)`, `first_seen`, `last_seen` |
| `failures` | `id`, `run_id`, `org_id`, `test_name`, `error_type`, `message`, `trace`, `fingerprint`, `embedding vector(384)`, `sanitized`, `defect_family_id`, `created_at` |

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

y `ingest_run` lanza `PermissionError` si el usuario no es miembro. Esto está **cubierto por tests de integración** contra el Supabase real (`tests/test_assurance_repository.py`): aislamiento cross-org, rechazo de no-miembro, y agrupación cross-proyecto.

`FORCE RLS` queda como **red de seguridad** para el futuro (si se conecta vía un rol `authenticated` real / PostgREST en vez del rol pooler con BYPASS).

> **Defensa en profundidad:** todas las queries usan parámetros (`%s`, sin concatenación) → sin inyección SQL; y el filtro de membership es independiente de RLS.

## Conexión a Supabase

- Usar la cadena del **Session pooler** (puerto 5432): `postgresql://postgres.<ref>:<pass>@aws-X-<region>.pooler.supabase.com:5432/postgres`.
- La conexión **directa** `db.<ref>.supabase.co:5432` es **IPv6-only** en proyectos nuevos y puede dar "no route to host" desde redes sin IPv6 enrutable.
- `DATABASE_URL` va en `.env` (gitignored). `multi_tenant_enabled()` requiere `DATABASE_URL` y `SUPABASE_URL`; si faltan, los endpoints `/v2` responden 503.
