-- db/migrations/012_failure_location.sql
-- F3c-2: ubicación del test (file:line) para el self-heal → PR. El reporter ya
-- emite file/line (CiTestResult); aquí se persisten para localizar el archivo a editar.

alter table public.failures add column if not exists file text;
alter table public.failures add column if not exists line int;
