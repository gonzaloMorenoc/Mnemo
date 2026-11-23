-- Lo mínimo de Supabase que las migraciones dan por hecho, para un Postgres de PRUEBA
-- (CI y local con docker pgvector/pgvector). Nunca se ejecuta contra producción.
create extension if not exists vector;
create extension if not exists pgcrypto;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin; end if;
end $$;
create schema if not exists auth;
create table if not exists auth.users (
    id uuid primary key, email text, role text, aud text,
    created_at timestamptz, updated_at timestamptz, raw_user_meta_data jsonb
);
create or replace function auth.uid() returns uuid language sql stable as
  $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
create or replace function auth.jwt() returns jsonb language sql stable as
  $$ select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb $$;
