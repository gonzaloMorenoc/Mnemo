-- db/migrations/014_certificates.sql
-- Mnemo Autopilot F4a: Release Assurance Certificate (append-only, firmado).

create table if not exists public.certificates (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    canonical_json jsonb not null,
    signature text not null,
    verdict text not null check (verdict in ('apto', 'apto-con-reservas', 'no-apto')),
    risk_score int not null,
    sign_offs jsonb,
    mnemo_version text,
    model_version text,
    created_at timestamptz not null default now()
);
create index if not exists idx_certificates_run on public.certificates (run_id, created_at desc);

alter table public.certificates enable row level security;
alter table public.certificates force row level security;
drop policy if exists certificates_member on public.certificates;
create policy certificates_member on public.certificates for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert on public.certificates to authenticated;  -- append-only
