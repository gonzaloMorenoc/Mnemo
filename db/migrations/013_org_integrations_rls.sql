-- db/migrations/013_org_integrations_rls.sql
-- Hotfix de seguridad. La tabla public.org_integrations (credenciales por-org:
-- token de Jira cifrado, base_url/email/jql, y installation_id/repo_full_name de la
-- GitHub App) se creó en 005_jira_integration.sql SIN row-level security, a diferencia
-- del resto de tablas multitenant (002/007/009/010). Quedó accesible vía PostgREST con
-- la anon key (Supabase advisor: rls_disabled_in_public — CRITICAL).
--
-- Fix: habilitar RLS + force + política is_org_member(org_id), igual que las demás
-- tablas. El backend accede por el pooler (rol que bypasea RLS), así que no se ve
-- afectado; solo se bloquea el acceso directo no autorizado. Idempotente.

alter table public.org_integrations enable row level security;
alter table public.org_integrations force row level security;
drop policy if exists org_integrations_member on public.org_integrations;
create policy org_integrations_member on public.org_integrations for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
