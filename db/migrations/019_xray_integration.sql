-- db/migrations/019_xray_integration.sql
-- Añade soporte Xray (Cloud o Server/DC) a la tabla org_integrations existente.
-- Xray Cloud: autenticación client_id/client_secret → bearer en xray.cloud.getxray.app.
-- Xray Server/DC: autenticación Basic en el Jira propio (/rest/raven/...).
-- Se reutiliza la misma tabla multitenant (org_id + provider unique) y el mismo
-- patrón de cifrado Fernet que Jira/GitHub: client_secret va en api_token_enc.
-- El campo email se reutiliza para client_id; base_url para el host de Xray.
-- Un campo extra `xray_mode` (cloud|server) distingue el sabor de la API.

alter table public.org_integrations drop constraint if exists org_integrations_provider_check;
alter table public.org_integrations add constraint org_integrations_provider_check
    check (provider in ('jira', 'github', 'xray'));

alter table public.org_integrations add column if not exists xray_mode text
    check (xray_mode in ('cloud', 'server'));
