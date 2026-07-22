-- Curación del conocimiento (Fase 1): ciclo de vida + frescura.
-- `status`: 'obsoleto' se excluye de RAG/búsqueda/graph/gaps (pero sigue visible en
-- el hojeo, marcado). `updated_at`: se fija en cada edición (frescura).
-- Idempotente: docker_init re-aplica todas las migraciones en cada arranque.

alter table public.qa_knowledge
    add column if not exists status text not null default 'activo';
alter table public.qa_knowledge
    add column if not exists updated_at timestamptz;

alter table public.qa_knowledge drop constraint if exists qa_knowledge_status_chk;
alter table public.qa_knowledge add constraint qa_knowledge_status_chk
    check (status in ('activo','obsoleto'));

create index if not exists idx_qa_knowledge_org_status
    on public.qa_knowledge (org_id, status);
