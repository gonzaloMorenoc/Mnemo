-- db/migrations/011_github_integration.sql
-- F3c: integración GitHub App por-org (installation + repo destino) sobre org_integrations.
-- Además: FK de auditoría que faltaba en actions.approved_by (revisión de F3a).

alter table public.org_integrations drop constraint if exists org_integrations_provider_check;
alter table public.org_integrations add constraint org_integrations_provider_check
    check (provider in ('jira', 'github'));

alter table public.org_integrations add column if not exists installation_id text;
alter table public.org_integrations add column if not exists repo_full_name text;

-- github no usa estas columnas (la private key es global, en env) → nullable
alter table public.org_integrations alter column email drop not null;
alter table public.org_integrations alter column api_token_enc drop not null;
alter table public.org_integrations alter column jql drop not null;

alter table public.actions drop constraint if exists actions_approved_by_fkey;
alter table public.actions add constraint actions_approved_by_fkey
    foreign key (approved_by) references auth.users (id) on delete set null;
