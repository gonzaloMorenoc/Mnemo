-- Interruptor de LLM externo POR ORGANIZACIÓN (auditoría 23-nov, #17 / H5).
--
-- ALLOW_EXTERNAL_LLM es global: un cliente no podía excluirse de un proveedor
-- externo (Groq, EE. UU.). Si una org desactiva `allow_external_llm`, sus funciones
-- de IA degradan como «sin LLM» (la vía determinista que ya existe). Sin fila = se
-- aplica la política global (por defecto permitido), así no cambia nada hasta que
-- un admin lo desactive.
--
-- Tabla aparte (no columna en organizations) para no chocar con otras migraciones
-- que tocan organizations. Idempotente: scripts/docker_init.py re-aplica todo.

create table if not exists public.org_llm_settings (
    org_id uuid primary key references public.organizations (id) on delete cascade,
    allow_external_llm boolean not null default true,
    updated_by uuid,
    updated_at timestamptz not null default now()
);

alter table public.org_llm_settings enable row level security;
alter table public.org_llm_settings force row level security;

-- Lectura: cualquier miembro. Escritura: solo owner/admin (patrón de ingest_tokens).
drop policy if exists org_llm_settings_select on public.org_llm_settings;
create policy org_llm_settings_select on public.org_llm_settings for select
    using (public.is_org_member(org_id));
drop policy if exists org_llm_settings_admin_insert on public.org_llm_settings;
create policy org_llm_settings_admin_insert on public.org_llm_settings for insert
    with check (public.is_org_admin(org_id));
drop policy if exists org_llm_settings_admin_update on public.org_llm_settings;
create policy org_llm_settings_admin_update on public.org_llm_settings for update
    using (public.is_org_admin(org_id)) with check (public.is_org_admin(org_id));
drop policy if exists org_llm_settings_admin_delete on public.org_llm_settings;
create policy org_llm_settings_admin_delete on public.org_llm_settings for delete
    using (public.is_org_admin(org_id));

-- SIN grants a anon/authenticated: el ajuste se gestiona SIEMPRE por la API de la app.
revoke all on public.org_llm_settings from anon, authenticated;
