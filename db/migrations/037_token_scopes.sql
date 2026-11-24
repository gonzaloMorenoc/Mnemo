-- Tokens con ámbito (plan «brain» 23-nov, frente C): además de los de ingesta del CI,
-- tokens de SOLO LECTURA para asistentes de IA por MCP (Claude Code, Cursor, Copilot).
--
-- * `scopes`: los tokens existentes quedan `{ingest}` (el default), así que nada cambia
--   para los CI ya conectados. Un token de lectura lleva `{read}` y otro prefijo
--   (`mnemo_rt_`): el código anterior —que solo acepta `mnemo_it_`— lo rechaza por
--   formato aunque convivan unos minutos durante el despliegue.
-- * `project`: opcional; si está, el token solo ve ese proyecto (+ lo de toda la org).
--   FK a `projects` (036): no se puede atar un token a un proyecto que no existe.
-- * `expires_at`: opcional; caducado = inválido, igual que revocado.

alter table public.ingest_tokens
    add column if not exists scopes text[] not null default '{ingest}',
    add column if not exists project text,
    add column if not exists expires_at timestamptz;

alter table public.ingest_tokens drop constraint if exists ingest_tokens_scopes_check;
alter table public.ingest_tokens add constraint ingest_tokens_scopes_check
    check (cardinality(scopes) >= 1 and scopes <@ array['ingest', 'read']::text[]);

alter table public.ingest_tokens drop constraint if exists ingest_tokens_project_fk;
alter table public.ingest_tokens add constraint ingest_tokens_project_fk
    foreign key (org_id, project) references public.projects (org_id, key);

-- «¿Qué sabe el equipo de este test?» busca fallos por nombre del test dentro de la org.
create index if not exists idx_failures_org_test_name
    on public.failures (org_id, lower(test_name));
