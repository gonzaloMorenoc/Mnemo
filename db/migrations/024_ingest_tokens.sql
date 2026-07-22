-- Tokens de ingesta CI por organización: "cualquier CI se enchufa con un token".
-- El token en claro se muestra UNA vez al crearlo; aquí solo vive su hash (sha256).
-- El token actúa con la identidad de quien lo creó (created_by) → los membership
-- checks del pipeline aplican tal cual. Idempotente (docker_init re-aplica todo).

create table if not exists public.ingest_tokens (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    name text not null,
    token_hash text not null unique,
    created_by uuid not null,
    created_at timestamptz not null default now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);

create index if not exists idx_ingest_tokens_org on public.ingest_tokens (org_id);

alter table public.ingest_tokens enable row level security;
alter table public.ingest_tokens force row level security;

-- Es una tabla de CREDENCIALES, no de contenido: la escritura exige rol admin
-- (patrón de `memberships`, is_org_admin) y el insert queda atado a auth.uid()
-- — con is_org_member a secas, cualquier member podría forjar/reactivar tokens
-- vía PostgREST directo saltándose el gate owner/admin de la app.
drop policy if exists ingest_tokens_member on public.ingest_tokens;
drop policy if exists ingest_tokens_select on public.ingest_tokens;
create policy ingest_tokens_select on public.ingest_tokens for select
    using (public.is_org_member(org_id));
drop policy if exists ingest_tokens_admin_insert on public.ingest_tokens;
create policy ingest_tokens_admin_insert on public.ingest_tokens for insert
    with check (public.is_org_admin(org_id) and created_by = auth.uid());
drop policy if exists ingest_tokens_admin_update on public.ingest_tokens;
create policy ingest_tokens_admin_update on public.ingest_tokens for update
    using (public.is_org_admin(org_id)) with check (public.is_org_admin(org_id));
drop policy if exists ingest_tokens_admin_delete on public.ingest_tokens;
create policy ingest_tokens_admin_delete on public.ingest_tokens for delete
    using (public.is_org_admin(org_id));

-- SIN grants al rol authenticated: la gestión va SIEMPRE por la API de la app
-- (el pooler no los necesita). Evita además exponer token_hash por PostgREST.
