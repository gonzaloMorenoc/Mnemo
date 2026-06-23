-- db/migrations/008_run_uid.sql
-- Mnemo Autopilot F2a: idempotencia de ingesta por identificador de run del CI.
-- run_uid es un UUID que el reporter genera UNA vez por run. Dedup por (org_id, run_uid):
-- un reintento de la misma entrega → no-op; una re-ejecución (mismo commit, otro run) → run nuevo.
-- El índice es PARCIAL: los runs sin run_uid (caminos legacy) no se ven afectados.

alter table public.test_runs add column if not exists run_uid text;

create unique index if not exists idx_test_runs_run_uid
    on public.test_runs (org_id, run_uid)
    where run_uid is not null;
