-- Mnemo: esquema de aseguramiento (runs, failures, defect families)
create extension if not exists vector;

create table if not exists public.test_runs (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    project text not null,
    source text not null check (source in ('allure', 'junit')),
    ci_ref text,
    summary jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.defect_families (
    id uuid primary key default gen_random_uuid(),
    scope text not null check (scope in ('org', 'global')),
    org_id uuid references public.organizations (id) on delete cascade,
    signature text not null,
    title text not null,
    root_cause text,
    status text not null default 'open' check (status in ('open', 'resolved')),
    occurrence_count int not null default 0,
    centroid vector(384),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint defect_families_scope_chk check (
        (scope = 'org' and org_id is not null) or (scope = 'global' and org_id is null)
    )
);

create table if not exists public.failures (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    test_name text not null,
    error_type text,
    message text not null,
    trace text,
    fingerprint text not null,
    embedding vector(384),
    sanitized boolean not null default false,
    defect_family_id uuid references public.defect_families (id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists idx_runs_org on public.test_runs (org_id);
create index if not exists idx_failures_org on public.failures (org_id);
create index if not exists idx_failures_family on public.failures (defect_family_id);
create index if not exists idx_failures_fingerprint on public.failures (fingerprint);
create index if not exists idx_failures_embedding on public.failures using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists idx_families_org on public.defect_families (org_id) where org_id is not null;
create index if not exists idx_families_signature on public.defect_families (signature);

alter table public.test_runs enable row level security;
alter table public.failures enable row level security;
alter table public.defect_families enable row level security;
alter table public.test_runs force row level security;
alter table public.failures force row level security;
alter table public.defect_families force row level security;

drop policy if exists test_runs_member on public.test_runs;
create policy test_runs_member on public.test_runs for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

drop policy if exists failures_member on public.failures;
create policy failures_member on public.failures for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

drop policy if exists defect_families_rw on public.defect_families;
create policy defect_families_rw on public.defect_families for all
    using (scope = 'global' or public.is_org_member(org_id))
    with check (scope = 'org' and public.is_org_member(org_id));

grant select, insert, update, delete on public.test_runs to authenticated;
grant select, insert, update, delete on public.failures to authenticated;
grant select, insert, update, delete on public.defect_families to authenticated;
