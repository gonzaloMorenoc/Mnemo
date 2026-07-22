-- Índice en failures.run_id (Postgres NO indexa FKs automáticamente).
-- Lo necesita el conteo por run del histórico (GET /v2/runs hace un count
-- correlacionado por fila) y cualquier lectura run-scoped de failures; sin él,
-- cada fila del histórico provocaba un seq-scan de failures. Idempotente.

create index if not exists idx_failures_run_id on public.failures (run_id);
