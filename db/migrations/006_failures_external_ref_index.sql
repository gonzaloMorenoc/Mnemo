-- db/migrations/006_failures_external_ref_index.sql
-- Índice para el dedup de imports de Jira (existing_external_refs): evita un
-- seq scan creciente de public.failures al filtrar por (org_id, external_ref).
create index if not exists idx_failures_org_external_ref
    on public.failures (org_id, external_ref)
    where external_ref is not null;
