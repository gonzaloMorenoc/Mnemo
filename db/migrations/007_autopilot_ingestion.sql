-- db/migrations/007_autopilot_ingestion.sql
-- Mnemo Autopilot F1: cimientos de ingesta viva.
--   test_runs.commit_sha → atar un run a un commit (señal flaky mismo-SHA en F2)
--   test_results          → resultado por test/run (incluye pass) para intermitencia
--   dom_snapshots         → snapshot DOM por test (último verde / fallo) para self-heal (F3)

alter table public.test_runs add column if not exists commit_sha text;

create table if not exists public.test_results (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    test_name text not null,
    status text not null check (status in ('pass', 'fail', 'flaky', 'skipped')),
    retried boolean not null default false,
    created_at timestamptz not null default now()
);

create table if not exists public.dom_snapshots (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    project text not null,
    test_name text not null,
    kind text not null check (kind in ('last_green', 'failure')),
    content text not null,
    commit_sha text,
    created_at timestamptz not null default now()
);

create index if not exists idx_test_results_run on public.test_results (run_id);
create index if not exists idx_test_results_org on public.test_results (org_id);
create index if not exists idx_test_results_name on public.test_results (org_id, test_name);
create index if not exists idx_dom_snapshots_lookup
    on public.dom_snapshots (org_id, project, test_name, kind);

alter table public.test_results enable row level security;
alter table public.dom_snapshots enable row level security;
alter table public.test_results force row level security;
alter table public.dom_snapshots force row level security;

drop policy if exists test_results_member on public.test_results;
create policy test_results_member on public.test_results for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

drop policy if exists dom_snapshots_member on public.dom_snapshots;
create policy dom_snapshots_member on public.dom_snapshots for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

grant select, insert, update, delete on public.test_results to authenticated;
grant select, insert, update, delete on public.dom_snapshots to authenticated;
