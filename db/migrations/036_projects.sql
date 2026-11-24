-- Proyecto como entidad (plan «brain» 23-nov, frente A).
--
-- Hasta ahora `project` era texto libre en 5 tablas. Ahora cada (org, proyecto) tiene
-- una fila en `projects` con un nombre visible editable, descripción y archivado.
--
-- Reglas de diseño (ver docs/auditoria/2026-11-23-brain-qa/06-plan-brain.md):
-- * La CLAVE es el texto que ya había y es INMUTABLE: el acta firmada lleva `project`
--   dentro del JSON firmado y la huella del depósito se calcula por proyecto, así que
--   renombrarla descuadraría actas. Lo editable es `name`.
-- * Los `null` (conocimiento de toda la organización) NO se convierten en un proyecto:
--   alteraría el depósito firmado de proyectos existentes. Quedan fuera de la FK.
-- * Compatible con el código anterior durante el despliegue (migraciones antes de
--   reconstruir el backend): las ingestas del código viejo no conocen `projects`, así
--   que un TRIGGER crea la fila si falta antes de que la FK la exija.

create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    -- Sin restricción de forma en la clave: cualquier texto que ya usen las 5 tablas
    -- tiene que caber (un CHECK aquí rompería la migración o una ingesta del código
    -- viejo). Las claves NUEVAS las valida la API.
    key text not null,
    name text not null check (length(name) between 1 and 200),
    description text check (description is null or length(description) <= 2000),
    is_example boolean not null default false,
    created_at timestamptz not null default now(),
    archived_at timestamptz,
    unique (org_id, key)
);

-- Nombre visible inicial: la clave recortada; si no tiene nada visible, un marcador.
create or replace function public.project_default_name(project_key text)
returns text
language sql
immutable
set search_path = public, pg_temp
as $$ select coalesce(nullif(btrim(left(project_key, 200)), ''), '(sin nombre)') $$;

-- Sin escrituras en las 5 tablas mientras se rellena y se crean triggers y FK: una
-- ingesta con un proyecto nuevo entre el relleno y el trigger haría fallar la FK.
-- (Milisegundos con los volúmenes actuales; las lecturas siguen.)
lock table public.test_runs, public.dom_snapshots, public.qa_knowledge,
           public.knowledge_proposals, public.handover_acts in share row exclusive mode;

-- En conocimiento y propuestas, un proyecto en blanco = de toda la organización.
update public.qa_knowledge set project = null
    where project is not null and btrim(project) = '';
update public.knowledge_proposals set project = null
    where project is not null and btrim(project) = '';

-- Una fila por (org, proyecto) que ya exista en cualquiera de las 5 tablas.
insert into public.projects (org_id, key, name)
select distinct org_id, project, public.project_default_name(project) from (
    select org_id, project from public.test_runs
    union select org_id, project from public.dom_snapshots
    union select org_id, project from public.qa_knowledge
    union select org_id, project from public.knowledge_proposals
    union select org_id, project from public.handover_acts
) p
where org_id is not null and project is not null
on conflict (org_id, key) do nothing;

-- Crea el proyecto si falta (ingestas, imports, código anterior). Seguro con shards de
-- CI en paralelo: `on conflict do nothing`. SECURITY DEFINER + search_path fijo: corre
-- igual sea cual sea el rol que inserta.
create or replace function public.ensure_project_row()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    -- Conocimiento y propuestas: «» o solo espacios = de toda la organización (null).
    if tg_table_name in ('qa_knowledge', 'knowledge_proposals')
       and new.project is not null and btrim(new.project) = '' then
        new.project := null;
    end if;
    if new.project is not null and new.org_id is not null then
        insert into public.projects (org_id, key, name)
        values (new.org_id, new.project, public.project_default_name(new.project))
        on conflict (org_id, key) do nothing;
    end if;
    return new;
end;
$$;

do $$
declare
    t text;
begin
    foreach t in array array['test_runs', 'dom_snapshots', 'qa_knowledge',
                             'knowledge_proposals', 'handover_acts'] loop
        execute format('drop trigger if exists ensure_project on public.%I', t);
        execute format('create trigger ensure_project before insert or update of project, org_id'
                       ' on public.%I for each row execute function public.ensure_project_row()', t);
        execute format('alter table public.%I drop constraint if exists %I', t, t || '_project_fk');
        -- FK compuesta: (org_id, project) existe en projects. MATCH SIMPLE: con project
        -- null no se comprueba (conocimiento de toda la org). Sin on update/delete: la
        -- clave no se renombra y un proyecto se archiva, no se borra.
        execute format('alter table public.%I add constraint %I foreign key (org_id, project)'
                       ' references public.projects (org_id, key)', t, t || '_project_fk');
    end loop;
end $$;

-- Índices para «por proyecto»: listados con recuentos, la propia FK y el filtro de
-- búsqueda. test_runs solo tenía uno parcial por commit, que no sirve aquí.
create index if not exists idx_test_runs_org_project
    on public.test_runs (org_id, project, created_at desc);
create index if not exists idx_qa_knowledge_org_project
    on public.qa_knowledge (org_id, project);
create index if not exists idx_knowledge_proposals_org_project
    on public.knowledge_proposals (org_id, project);

alter table public.projects enable row level security;
alter table public.projects force row level security;

drop policy if exists projects_select on public.projects;
create policy projects_select on public.projects for select
    using (public.is_org_member(org_id));
drop policy if exists projects_admin_write on public.projects;
create policy projects_admin_write on public.projects for all
    using (public.is_org_admin(org_id)) with check (public.is_org_admin(org_id));

-- Sin grants a anon/authenticated: se gestiona SIEMPRE por la API (y la 999 lo reafirma).
revoke all on public.projects from anon, authenticated;
