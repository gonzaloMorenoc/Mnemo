-- El CHECK de verdict aprende `sin_confirmar` (rename inconcluso→sin_confirmar, PR #95).
--
-- El motor (src/certify/certificate.py::compute_verdict) emite `sin_confirmar` cuando
-- un run limpio no puede confirmar su ejecución (manifiesto ausente o incompleto),
-- pero el CHECK de 014 solo admitía los 3 veredictos originales: el INSERT del acta
-- moría con CheckViolation y el endpoint de certificar respondía 502. Detectado al
-- re-emitir las actas de la demo: 13 runs sin manifiesto no se podían certificar.
--
-- Aditiva: el set nuevo es superconjunto del anterior, ninguna fila existente viola
-- el CHECK nuevo y no hay datos que migrar.
--
-- `if exists` porque scripts/docker_init.py re-aplica todas las migraciones en cada
-- arranque: la migración tiene que poder ejecutarse dos veces sin romper.

alter table public.certificates drop constraint if exists certificates_verdict_check;
alter table public.certificates add constraint certificates_verdict_check
    check (verdict in ('apto', 'apto-con-reservas', 'no-apto', 'sin_confirmar'));
