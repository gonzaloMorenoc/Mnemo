-- db/migrations/005_jira_integration.sql
-- Integra bugs de Jira en el Defect DNA: amplía source, añade trazabilidad y
-- guarda las credenciales por org (token cifrado en capa de app).
alter table public.test_runs drop constraint if exists test_runs_source_check;
alter table public.test_runs add constraint test_runs_source_check
    check (source in ('allure', 'junit', 'testng', 'cucumber', 'playwright', 'cypress', 'robot', 'jira'));

alter table public.failures add column if not exists external_ref text;
alter table public.failures add column if not exists external_url text;

create table if not exists public.org_integrations (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    provider text not null check (provider in ('jira')),
    base_url text not null,
    email text not null,
    api_token_enc text not null,
    jql text not null default 'issuetype = Bug',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, provider)
);
create index if not exists idx_org_integrations_org on public.org_integrations (org_id);
