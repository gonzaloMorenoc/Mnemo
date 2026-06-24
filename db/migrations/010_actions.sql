-- db/migrations/010_actions.sql
-- Mnemo Autopilot F3a: acciones propuestas (Nivel 2) sobre los veredictos de triaje.

create table if not exists public.actions (
    id uuid primary key default gen_random_uuid(),
    triage_verdict_id uuid not null references public.triage_verdicts (id) on delete cascade,
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    kind text not null check (kind in ('quarantine', 'ticket', 'self_heal')),
    payload jsonb,
    summary text,
    status text not null default 'proposed'
        check (status in ('proposed', 'approved', 'rejected', 'materialized')),
    artifact_ref text,
    approved_by uuid,
    approved_at timestamptz,
    reject_reason text,
    created_at timestamptz not null default now()
);

create index if not exists idx_actions_run on public.actions (run_id);
create index if not exists idx_actions_org_status on public.actions (org_id, status);

alter table public.actions enable row level security;
alter table public.actions force row level security;
drop policy if exists actions_member on public.actions;
create policy actions_member on public.actions for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert, update, delete on public.actions to authenticated;
