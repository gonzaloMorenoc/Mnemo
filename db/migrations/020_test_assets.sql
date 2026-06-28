create extension if not exists vector;

create table if not exists public.test_assets (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    repo_full_name text not null,
    path text not null,
    framework text,
    domain text,
    content text not null,
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists idx_test_assets_org on public.test_assets (org_id);
create index if not exists idx_test_assets_domain on public.test_assets (org_id, domain) where domain is not null;
create index if not exists idx_test_assets_embedding on public.test_assets
    using ivfflat (embedding vector_cosine_ops) with (lists = 100) where embedding is not null;

alter table public.test_assets enable row level security;
alter table public.test_assets force row level security;
create policy test_assets_member on public.test_assets
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
