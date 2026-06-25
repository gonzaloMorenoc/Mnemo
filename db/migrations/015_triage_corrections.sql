-- db/migrations/015_triage_corrections.sql
-- Mnemo Autopilot F5a: historia auditable del lazo de aprendizaje (motor vs humano).

create table if not exists public.triage_corrections (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    family_id uuid not null references public.defect_families (id) on delete cascade,
    engine_category text,
    human_category text not null,
    source text not null default 'family_label',
    reason text,
    corrected_by uuid references auth.users (id),
    corrected_at timestamptz not null default now()
);
create index if not exists idx_triage_corrections_org on public.triage_corrections (org_id, corrected_at desc);

alter table public.triage_corrections enable row level security;
alter table public.triage_corrections force row level security;
drop policy if exists triage_corrections_member on public.triage_corrections;
create policy triage_corrections_member on public.triage_corrections for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert on public.triage_corrections to authenticated;  -- append-only
