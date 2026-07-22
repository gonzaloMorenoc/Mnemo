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
drop policy if exists ingest_tokens_member on public.ingest_tokens;
create policy ingest_tokens_member on public.ingest_tokens for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

grant select, insert, update, delete on public.ingest_tokens to authenticated;
