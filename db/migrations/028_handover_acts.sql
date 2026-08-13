-- Actas de traspaso (paso 3 de la auditoría 12-ago): al rotar a un consultor, la
-- consultora emite un acta firmada de que el conocimiento del proyecto quedó
-- depositado. Conecta los dos pilares del producto — memoria y firma.
--
-- Tabla PROPIA a propósito: public.certificates tiene run_id NOT NULL y un CHECK de
-- veredicto que son parte de la garantía del acta de release. Debilitarlos para
-- acomodar el traspaso contaminaría ambos modelos.
--
-- score es nullable: «sin datos suficientes» se firma igual (un acta honesta que
-- dice que no hay nada vale más que un cero inventado).

create table if not exists public.handover_acts (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    project text not null,
    canonical_json jsonb not null,
    signature text not null,
    score int,
    created_by uuid not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_handover_org_project
    on public.handover_acts (org_id, project, created_at desc);

-- Invariante RLS del repo: toda tabla en public lleva enable + force + policy
-- is_org_member, o queda expuesta vía PostgREST con la anon key. drop+create
-- porque docker_init re-aplica TODAS las migraciones en cada arranque y
-- `create policy` no admite `if not exists` (patrón de 013/024).
alter table public.handover_acts enable row level security;
alter table public.handover_acts force row level security;
drop policy if exists handover_acts_member on public.handover_acts;
create policy handover_acts_member on public.handover_acts for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
