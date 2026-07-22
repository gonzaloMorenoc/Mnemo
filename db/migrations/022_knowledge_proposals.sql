-- Propuestas de conocimiento para la memoria de QA ("IA propone / humano aprueba").
-- Una propuesta por familia de defecto (UNIQUE); ciclo de vida por `status`.
-- Al aprobar se crea el item real en public.qa_knowledge y la fila queda como
-- 'approved' (auditoría de quién/cuándo, patrón public.actions).

create table if not exists public.knowledge_proposals (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    -- Efímera sin su familia → CASCADE (a diferencia del item aprobado en qa_knowledge, que es SET NULL).
    defect_family_id uuid not null references public.defect_families (id) on delete cascade,
    run_id uuid references public.test_runs (id) on delete set null,
    kind text not null default 'leccion'
        check (kind in ('regla_negocio','flujo','riesgo','glosario','leccion','reto','patron')),
    title text not null,
    challenge text,
    approach text,
    domain text,
    outcome text,
    tags text[] not null default '{}',
    status text not null default 'pending' check (status in ('pending','approved','rejected')),
    approved_by uuid,
    approved_at timestamptz,
    reject_reason text,
    created_by uuid not null,
    created_at timestamptz not null default now(),
    unique (defect_family_id)
);

create index if not exists idx_knowledge_proposals_org_status
    on public.knowledge_proposals (org_id, status);
create index if not exists idx_knowledge_proposals_run
    on public.knowledge_proposals (run_id) where run_id is not null;

alter table public.knowledge_proposals enable row level security;
alter table public.knowledge_proposals force row level security;
-- drop antes del create → la migración es idempotente (docker_init re-aplica todas
-- las migraciones en cada arranque; CREATE POLICY sin drop lanzaría al re-ejecutar).
drop policy if exists knowledge_proposals_member on public.knowledge_proposals;
create policy knowledge_proposals_member on public.knowledge_proposals for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

grant select, insert, update, delete on public.knowledge_proposals to authenticated;
