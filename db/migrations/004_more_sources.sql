-- db/migrations/004_more_sources.sql
-- Amplía los formatos de reporte admitidos en test_runs.source.
alter table public.test_runs drop constraint if exists test_runs_source_check;
alter table public.test_runs add constraint test_runs_source_check
    check (source in ('allure', 'junit', 'testng', 'cucumber', 'playwright', 'cypress', 'robot'));
