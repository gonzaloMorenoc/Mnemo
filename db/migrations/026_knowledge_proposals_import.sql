-- Import de conocimiento (Jira/Confluence) a la bandeja "IA propone / humano aprueba".
-- Idempotente: docker_init re-aplica todas las migraciones en cada arranque, en orden;
-- el grant de la 022 se re-aplica antes que este revoke → estado final = revocado.

-- 1) La familia deja de ser obligatoria (los imports no tienen familia).
--    NO tocar unique(defect_family_id): admite múltiples NULL, y el
--    ON CONFLICT (defect_family_id) del auto-triaje solo infiere índices NO parciales.
alter table public.knowledge_proposals
    alter column defect_family_id drop not null;

-- 2) Procedencia, referencia externa y proyecto del draft.
alter table public.knowledge_proposals
    add column if not exists source text not null default 'auto_triage';
alter table public.knowledge_proposals
    add column if not exists external_ref text;
alter table public.knowledge_proposals
    add column if not exists external_url text;
alter table public.knowledge_proposals
    add column if not exists project text;
-- Sello de import (insert Y refresh) para el tope horario: created_at no cambia
-- en el DO UPDATE, así que no sirve para contar refrescos.
alter table public.knowledge_proposals
    add column if not exists imported_at timestamptz;

alter table public.knowledge_proposals drop constraint if exists knowledge_proposals_source_chk;
alter table public.knowledge_proposals add constraint knowledge_proposals_source_chk
    check (source in ('auto_triage','jira','confluence'));

-- Ancla: triaje ⇒ familia; import ⇒ ref externa (un import PUEDE llevar familia — PR3).
alter table public.knowledge_proposals drop constraint if exists knowledge_proposals_anchor_chk;
alter table public.knowledge_proposals add constraint knowledge_proposals_anchor_chk
    check ((source = 'auto_triage' and defect_family_id is not null)
        or (source <> 'auto_triage' and external_ref is not null));

-- 3) Dedupe del import: una propuesta por (org, ref) para TODOS los status.
create unique index if not exists uq_knowledge_proposals_org_external_ref
    on public.knowledge_proposals (org_id, external_ref)
    where external_ref is not null;

-- 4) qa_knowledge conserva el enlace al original al aprobar.
alter table public.qa_knowledge
    add column if not exists source_url text;

-- 5) Cerrar la superficie REST de escritura: la app escribe siempre vía API/pooler
--    (el frontend solo usa supabase-js para auth). Un miembro podía fabricar
--    propuestas vía PostgREST con created_by/URL arbitrarios.
revoke insert, update, delete on public.knowledge_proposals from authenticated;
