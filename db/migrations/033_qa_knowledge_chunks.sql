-- Embeddings por fragmento del conocimiento largo (auditoría 23-nov-2026, #9).
--
-- El embedder (paraphrase-multilingual-MiniLM-L12-v2) trunca a 128 tokens y una
-- sección importada llega a 4.000 caracteres: a partir de ~100 palabras el texto
-- no era buscable. Cada item conserva su qa_knowledge.embedding y, si no cabe en
-- uno, guarda aquí un embedding por fragmento (src/knowledge/chunking.py). La
-- búsqueda toma, por item, la distancia mínima entre su embedding y sus fragmentos.
--
-- No se guarda el texto del fragmento: es derivable del item y duplicarlo
-- abriría otra copia del contenido que mantener (y que borrar).
-- Sin índice vectorial: el volumen por org es de cientos de fragmentos y un
-- ivfflat global con filtro por org pierde resultados (auditoría 23-nov, L7).
--
-- Aditiva: los items existentes no tienen fragmentos hasta que se editen o se
-- ejecute `python3 -m scripts.reembed`; mientras, se buscan como antes.
-- Idempotente (`if not exists` + drop/create policy): scripts/docker_init.py
-- re-aplica todas las migraciones en cada arranque.

create table if not exists public.qa_knowledge_chunks (
    id uuid primary key default gen_random_uuid(),
    knowledge_id uuid not null references public.qa_knowledge (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    chunk_index int not null check (chunk_index >= 0),
    embedding vector(384) not null,
    created_at timestamptz not null default now(),
    unique (knowledge_id, chunk_index)
);

create index if not exists idx_qa_knowledge_chunks_org
    on public.qa_knowledge_chunks (org_id);

-- Invariante RLS del repo: toda tabla en public lleva enable + force + policy
-- is_org_member, o queda expuesta vía PostgREST con la anon key.
alter table public.qa_knowledge_chunks enable row level security;
alter table public.qa_knowledge_chunks force row level security;
drop policy if exists qa_knowledge_chunks_member on public.qa_knowledge_chunks;
create policy qa_knowledge_chunks_member on public.qa_knowledge_chunks for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
