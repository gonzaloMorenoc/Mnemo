-- db/migrations/009_triage.sql
-- Mnemo Autopilot F2d: persistencia de veredictos de triaje + etiqueta de familia.

alter table public.defect_families
    add column if not exists label text not null default 'unknown'
    check (label in ('flaky', 'real', 'maintenance', 'infra', 'unknown'));

create table if not exists public.triage_verdicts (
    id uuid primary key default gen_random_uuid(),
    failure_id uuid not null references public.failures (id) on delete cascade,
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    category text not null check (category in ('flaky', 'infra', 'maintenance', 'real', 'unknown')),
    confidence real not null,
    rule_applied text not null,
    evidence_bundle jsonb,
    requires_approval boolean not null default false,
    llm_assisted boolean not null default false,
    status text not null default 'resolved' check (status in ('resolved', 'needs_tiebreak')),
    created_at timestamptz not null default now()
);

create index if not exists idx_triage_verdicts_run on public.triage_verdicts (run_id);
create index if not exists idx_triage_verdicts_org on public.triage_verdicts (org_id);

alter table public.triage_verdicts enable row level security;
alter table public.triage_verdicts force row level security;
drop policy if exists triage_verdicts_member on public.triage_verdicts;
create policy triage_verdicts_member on public.triage_verdicts for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert, update, delete on public.triage_verdicts to authenticated;
