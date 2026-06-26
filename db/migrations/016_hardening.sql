-- db/migrations/016_hardening.sql
-- Tanda 1 (auditoría 2026-06-25): force RLS en las tablas base de 001, índices FK
-- en hot paths, is_org_member hoisteable, e ivfflat parciales (excluir NULLs).

-- B1: las 7 tablas de 001 tenían enable pero NO force. RLS no aplicaba al owner.
alter table public.profiles      force row level security;
alter table public.organizations force row level security;
alter table public.memberships   force row level security;
alter table public.documents     force row level security;
alter table public.chunks        force row level security;
alter table public.embeddings    force row level security;
alter table public.analyses      force row level security;

-- A8: subconsulta para que el planner pueda hoistar auth.uid() (no per-row).
create or replace function public.is_org_member(target_org_id uuid)
returns boolean
language sql
stable
as $$
    select exists (
        select 1 from public.memberships m
        where m.org_id = target_org_id
          and m.user_id = (select auth.uid())
    );
$$;

-- A6: índices FK faltantes en hot paths.
create index if not exists idx_triage_verdicts_failure on public.triage_verdicts (failure_id);
create index if not exists idx_actions_verdict on public.actions (triage_verdict_id);
create index if not exists idx_triage_corrections_family on public.triage_corrections (family_id);
create index if not exists idx_test_runs_commit on public.test_runs (org_id, project, commit_sha)
    where commit_sha is not null;
create index if not exists idx_certificates_org on public.certificates (org_id);

-- A9: ivfflat parciales (el índice ya no almacena filas con NULL).
drop index if exists public.idx_failures_embedding;
create index if not exists idx_failures_embedding on public.failures
    using ivfflat (embedding vector_cosine_ops) with (lists = 100)
    where embedding is not null;
drop index if exists public.idx_families_centroid;
create index if not exists idx_families_centroid on public.defect_families
    using ivfflat (centroid vector_cosine_ops) with (lists = 100)
    where centroid is not null;
