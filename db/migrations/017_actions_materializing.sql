-- db/migrations/017_actions_materializing.sql
-- Tanda 1 (B2): estado intermedio 'materializing' para serializar la materialización
-- de acciones (approved → materializing → materialized). Atomicidad approve→materialize.
alter table public.actions drop constraint if exists actions_status_check;
alter table public.actions add constraint actions_status_check
    check (status in ('proposed', 'approved', 'rejected', 'materialized', 'materializing'));
