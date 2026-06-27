create extension if not exists vector;

create table if not exists public.qa_knowledge (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    kind text not null check (kind in ('regla_negocio','flujo','riesgo','glosario','leccion','reto','patron')),
    title text not null,
    challenge text,
    approach text,
    outcome text,
    domain text,
    tags text[] not null default '{}',
    project text,
    source text not null default 'manual',
    confidence text not null default 'confirmado' check (confidence in ('confirmado','inferido')),
    defect_family_id uuid references public.defect_families (id) on delete set null,
    run_id uuid references public.test_runs (id) on delete set null,
    created_by uuid not null,
    created_at timestamptz not null default now(),
    embedding vector(384)
);

create index if not exists idx_qa_knowledge_org on public.qa_knowledge (org_id);
create index if not exists idx_qa_knowledge_domain on public.qa_knowledge (org_id, domain) where domain is not null;
create index if not exists idx_qa_knowledge_embedding on public.qa_knowledge
    using ivfflat (embedding vector_cosine_ops) with (lists = 100) where embedding is not null;

alter table public.qa_knowledge enable row level security;
alter table public.qa_knowledge force row level security;
create policy qa_knowledge_member on public.qa_knowledge for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
