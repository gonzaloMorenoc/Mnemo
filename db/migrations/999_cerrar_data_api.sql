-- Cierra la Data API de Supabase (PostgREST) sobre el esquema public.
--
-- Por qué (auditoría 23-nov-2026, hallazgo #1, CRÍTICO): con la clave anónima pública y el
-- JWT de cualquier usuario, PostgREST permitía leer y ESCRIBIR las tablas de su organización
-- saltándose el backend: cambiar el base_url de Jira en org_integrations (y recibir el token
-- del cliente en la siguiente importación, sin pasar por el anti-SSRF), borrar o alterar
-- actas «append-only», o mover el commit_sha de un run verde para que el gate publicara
-- success en otro commit. Los grants a authenticated venían de las migraciones antiguas y de
-- los privilegios por defecto de Supabase sobre public.
--
-- Mnemo no usa la Data API: el frontend solo usa Supabase Auth y todo el acceso a datos va
-- por el backend FastAPI, que conecta con el rol del pooler (propietario, salta RLS). Las
-- políticas RLS se quedan como defensa en profundidad.
--
-- ESTA MIGRACIÓN DEBE SER SIEMPRE LA ÚLTIMA (de ahí el 999): el despliegue re-aplica todas
-- las migraciones en orden y varias antiguas vuelven a conceder permisos a authenticated;
-- esta las neutraliza cada vez. Un test (tests/test_migrations_data_api.py) lo comprueba.
-- Idempotente.

-- 1) Tablas, vistas y secuencias existentes: fuera todo para anon y authenticated.
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

-- 2) Funciones: Postgres concede EXECUTE a PUBLIC por defecto (incluye anon y authenticated),
--    así que hay que quitárselo también a PUBLIC para cerrar /rest/v1/rpc/*. El backend
--    llama a estas funciones como propietario y los triggers no comprueban EXECUTE al
--    dispararse, así que nada de la app depende de estos permisos.
--    SOLO las funciones de la app (propiedad del rol que migra): pgvector vive en public y
--    sus funciones son de supabase_admin; no se tocan (son matemáticas, sin datos).
do $$
declare
    fn record;
begin
    for fn in
        select p.oid::regprocedure as sig
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proowner = (select oid from pg_roles where rolname = current_user)
    loop
        execute format('revoke execute on function %s from public, anon, authenticated', fn.sig);
    end loop;
end
$$;

-- 3) Objetos futuros: que una tabla o función nueva no nazca expuesta otra vez.
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke execute on functions from anon, authenticated;
-- El EXECUTE a PUBLIC es un default GLOBAL (no de esquema): solo se quita sin «in schema».
alter default privileges revoke execute on functions from public;
