-- Multi-tenant KB schema for TraceFix / SmartErrorDebugger (Supabase + pgvector)
create extension if not exists vector;
create extension if not exists pgcrypto;

do $$
begin
    if not exists (select 1 from pg_type where typname = 'kb_scope') then
        create type public.kb_scope as enum ('global', 'user', 'org');
    end if;
    if not exists (select 1 from pg_type where typname = 'org_role') then
        create type public.org_role as enum ('owner', 'admin', 'member', 'viewer');
    end if;
end $$;

create table if not exists public.profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_name text,
    default_org_id uuid,
    created_at timestamptz not null default now()
);

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_by uuid not null references auth.users (id) on delete restrict,
    join_code text unique,
    created_at timestamptz not null default now()
);

alter table public.profiles
    drop constraint if exists profiles_default_org_id_fkey,
    add constraint profiles_default_org_id_fkey
    foreign key (default_org_id) references public.organizations (id) on delete set null;

create table if not exists public.memberships (
    org_id uuid not null references public.organizations (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role public.org_role not null default 'member',
    created_at timestamptz not null default now(),
    primary key (org_id, user_id)
);

create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    mime_type text,
    source_type text not null default 'upload',
    scope public.kb_scope not null,
    owner_user_id uuid references auth.users (id) on delete set null,
    org_id uuid references public.organizations (id) on delete cascade,
    storage_path text,
    contributed_to_global boolean not null default false,
    created_at timestamptz not null default now(),
    check (
        (scope = 'global' and owner_user_id is null and org_id is null)
        or (scope = 'user' and owner_user_id is not null and org_id is null)
        or (scope = 'org' and org_id is not null)
    )
);

create table if not exists public.chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references public.documents (id) on delete cascade,
    chunk_index integer not null,
    content text not null,
    sanitized_content text,
    scope public.kb_scope not null,
    owner_user_id uuid references auth.users (id) on delete set null,
    org_id uuid references public.organizations (id) on delete cascade,
    tech_tags text[] not null default '{}',
    error_type text,
    created_at timestamptz not null default now(),
    unique (document_id, chunk_index),
    check (
        (scope = 'global' and owner_user_id is null and org_id is null and sanitized_content is not null)
        or (scope = 'user' and owner_user_id is not null and org_id is null)
        or (scope = 'org' and org_id is not null)
    )
);

create table if not exists public.embeddings (
    id uuid primary key default gen_random_uuid(),
    chunk_id uuid not null unique references public.chunks (id) on delete cascade,
    embedding vector(384) not null,
    scope public.kb_scope not null,
    owner_user_id uuid references auth.users (id) on delete set null,
    org_id uuid references public.organizations (id) on delete cascade,
    created_at timestamptz not null default now(),
    check (
        (scope = 'global' and owner_user_id is null and org_id is null)
        or (scope = 'user' and owner_user_id is not null and org_id is null)
        or (scope = 'org' and org_id is not null)
    )
);

create table if not exists public.analyses (
    id bigserial primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    org_id uuid references public.organizations (id) on delete set null,
    input_error text not null,
    output jsonb not null,
    confidence real,
    source_scopes public.kb_scope[] not null default '{}',
    created_at timestamptz not null default now()
);

create index if not exists idx_memberships_user on public.memberships (user_id);
create index if not exists idx_documents_scope on public.documents (scope);
create index if not exists idx_documents_owner on public.documents (owner_user_id) where owner_user_id is not null;
create index if not exists idx_documents_org on public.documents (org_id) where org_id is not null;
create index if not exists idx_chunks_scope on public.chunks (scope);
create index if not exists idx_chunks_owner on public.chunks (owner_user_id) where owner_user_id is not null;
create index if not exists idx_chunks_org on public.chunks (org_id) where org_id is not null;
create index if not exists idx_chunks_tags on public.chunks using gin (tech_tags);
create index if not exists idx_embeddings_scope on public.embeddings (scope);
create index if not exists idx_embeddings_owner on public.embeddings (owner_user_id) where owner_user_id is not null;
create index if not exists idx_embeddings_org on public.embeddings (org_id) where org_id is not null;
create index if not exists idx_embeddings_vector_cosine on public.embeddings using ivfflat (embedding vector_cosine_ops) with (lists = 100);

create or replace function public.is_org_member(target_org_id uuid)
returns boolean
language sql
stable
as $$
    select exists (
        select 1
        from public.memberships m
        where m.org_id = target_org_id
          and m.user_id = auth.uid()
    );
$$;

create or replace function public.is_org_admin(target_org_id uuid)
returns boolean
language sql
stable
as $$
    select exists (
        select 1
        from public.memberships m
        where m.org_id = target_org_id
          and m.user_id = auth.uid()
          and m.role in ('owner', 'admin')
    );
$$;

create or replace function public.set_default_org_owner_membership()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if new.join_code is null then
        new.join_code := substring(replace(gen_random_uuid()::text, '-', '') from 1 for 10);
    end if;
    return new;
end;
$$;

drop trigger if exists trg_org_join_code on public.organizations;
create trigger trg_org_join_code
before insert on public.organizations
for each row
execute function public.set_default_org_owner_membership();

create or replace function public.create_owner_membership()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.memberships (org_id, user_id, role)
    values (new.id, new.created_by, 'owner')
    on conflict (org_id, user_id) do update set role = excluded.role;
    return new;
end;
$$;

drop trigger if exists trg_org_owner_membership on public.organizations;
create trigger trg_org_owner_membership
after insert on public.organizations
for each row
execute function public.create_owner_membership();

create or replace function public.join_organization_by_code(input_code text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    target_org uuid;
begin
    if auth.uid() is null then
        raise exception 'authenticated user required';
    end if;

    select o.id into target_org
    from public.organizations o
    where lower(o.join_code) = lower(input_code)
    limit 1;

    if target_org is null then
        raise exception 'invalid join code';
    end if;

    insert into public.memberships (org_id, user_id, role)
    values (target_org, auth.uid(), 'member')
    on conflict (org_id, user_id) do nothing;

    return target_org;
end;
$$;

create or replace function public.search_chunks_scoped(
    query_embedding vector(384),
    match_count int default 8
)
returns table (
    chunk_id uuid,
    document_id uuid,
    scope public.kb_scope,
    owner_user_id uuid,
    org_id uuid,
    source_title text,
    content text,
    similarity float4
)
language sql
stable
security invoker
as $$
    select
        c.id as chunk_id,
        c.document_id,
        c.scope,
        c.owner_user_id,
        c.org_id,
        d.title as source_title,
        case when c.scope = 'global' then coalesce(c.sanitized_content, c.content) else c.content end as content,
        (1 - (e.embedding <=> query_embedding))::float4 as similarity
    from public.embeddings e
    join public.chunks c on c.id = e.chunk_id
    join public.documents d on d.id = c.document_id
    order by
        case c.scope when 'org' then 0 when 'user' then 1 else 2 end,
        (e.embedding <=> query_embedding)
    limit greatest(match_count, 1);
$$;

alter table public.profiles enable row level security;
alter table public.organizations enable row level security;
alter table public.memberships enable row level security;
alter table public.documents enable row level security;
alter table public.chunks enable row level security;
alter table public.embeddings enable row level security;
alter table public.analyses enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
for select using (user_id = auth.uid());

drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles
for insert with check (user_id = auth.uid());

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
for update using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists org_select_member on public.organizations;
create policy org_select_member on public.organizations
for select using (public.is_org_member(id));

drop policy if exists org_insert_creator on public.organizations;
create policy org_insert_creator on public.organizations
for insert with check (created_by = auth.uid());

drop policy if exists org_update_admin on public.organizations;
create policy org_update_admin on public.organizations
for update using (public.is_org_admin(id));

drop policy if exists org_delete_owner on public.organizations;
create policy org_delete_owner on public.organizations
for delete using (
    exists (
        select 1
        from public.memberships m
        where m.org_id = id
          and m.user_id = auth.uid()
          and m.role = 'owner'
    )
);

drop policy if exists membership_select_visibility on public.memberships;
create policy membership_select_visibility on public.memberships
for select using (
    user_id = auth.uid()
    or public.is_org_member(org_id)
);

drop policy if exists membership_admin_insert on public.memberships;
create policy membership_admin_insert on public.memberships
for insert with check (
    public.is_org_admin(org_id)
);

drop policy if exists membership_admin_update on public.memberships;
create policy membership_admin_update on public.memberships
for update using (public.is_org_admin(org_id))
with check (public.is_org_admin(org_id));

drop policy if exists membership_admin_delete on public.memberships;
create policy membership_admin_delete on public.memberships
for delete using (public.is_org_admin(org_id));

drop policy if exists docs_scope_select on public.documents;
create policy docs_scope_select on public.documents
for select using (
    scope = 'global'
    or (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_member(org_id))
);

drop policy if exists docs_scope_insert on public.documents;
create policy docs_scope_insert on public.documents
for insert with check (
    (scope = 'global' and owner_user_id is null and org_id is null)
    or (scope = 'user' and owner_user_id = auth.uid() and org_id is null)
    or (scope = 'org' and owner_user_id = auth.uid() and public.is_org_member(org_id))
);

drop policy if exists docs_scope_update on public.documents;
create policy docs_scope_update on public.documents
for update using (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
)
with check (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
);

drop policy if exists docs_scope_delete on public.documents;
create policy docs_scope_delete on public.documents
for delete using (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
);

drop policy if exists chunks_scope_select on public.chunks;
create policy chunks_scope_select on public.chunks
for select using (
    scope = 'global'
    or (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_member(org_id))
);

drop policy if exists chunks_scope_insert on public.chunks;
create policy chunks_scope_insert on public.chunks
for insert with check (
    (scope = 'global' and owner_user_id is null and org_id is null and sanitized_content is not null)
    or (scope = 'user' and owner_user_id = auth.uid() and org_id is null)
    or (scope = 'org' and owner_user_id = auth.uid() and public.is_org_member(org_id))
);

drop policy if exists chunks_scope_update on public.chunks;
create policy chunks_scope_update on public.chunks
for update using (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
)
with check (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
);

drop policy if exists chunks_scope_delete on public.chunks;
create policy chunks_scope_delete on public.chunks
for delete using (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
);

drop policy if exists embeddings_scope_select on public.embeddings;
create policy embeddings_scope_select on public.embeddings
for select using (
    scope = 'global'
    or (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_member(org_id))
);

drop policy if exists embeddings_scope_insert on public.embeddings;
create policy embeddings_scope_insert on public.embeddings
for insert with check (
    (scope = 'global' and owner_user_id is null and org_id is null)
    or (scope = 'user' and owner_user_id = auth.uid() and org_id is null)
    or (scope = 'org' and owner_user_id = auth.uid() and public.is_org_member(org_id))
);

drop policy if exists embeddings_scope_update on public.embeddings;
create policy embeddings_scope_update on public.embeddings
for update using (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
)
with check (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
);

drop policy if exists embeddings_scope_delete on public.embeddings;
create policy embeddings_scope_delete on public.embeddings
for delete using (
    (scope = 'user' and owner_user_id = auth.uid())
    or (scope = 'org' and public.is_org_admin(org_id))
);

drop policy if exists analyses_scope_select on public.analyses;
create policy analyses_scope_select on public.analyses
for select using (
    user_id = auth.uid()
    or (org_id is not null and public.is_org_member(org_id))
);

drop policy if exists analyses_scope_insert on public.analyses;
create policy analyses_scope_insert on public.analyses
for insert with check (
    user_id = auth.uid()
    and (org_id is null or public.is_org_member(org_id))
);

grant execute on function public.join_organization_by_code(text) to authenticated;
grant execute on function public.search_chunks_scoped(vector, int) to authenticated;
grant select, insert, update, delete on public.profiles to authenticated;
grant select, insert, update, delete on public.organizations to authenticated;
grant select, insert, update, delete on public.memberships to authenticated;
grant select, insert, update, delete on public.documents to authenticated;
grant select, insert, update, delete on public.chunks to authenticated;
grant select, insert, update, delete on public.embeddings to authenticated;
grant select, insert, update, delete on public.analyses to authenticated;
grant usage, select on sequence public.analyses_id_seq to authenticated;
