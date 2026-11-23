-- 032 · Código de unión con caducidad y entrada como `viewer` (auditoría 23-nov, #11 / H3).
--
-- Antes: el código no caducaba, no se podía rotar y daba `member` (escritura) sin
-- aprobación. Ahora:
--   * `join_code_expires_at`: caduca (7 días por defecto; mismo valor que
--     JOIN_CODE_TTL_DAYS en src/orgs/repository.py, que lo usa al rotar).
--   * Quien se une entra como `viewer` (solo lectura); un admin lo sube de rol.
--   * La rotación la hace el backend (POST /v2/orgs/{id}/join-code/rotate, owner/admin).
--
-- Idempotente: el arranque re-aplica TODAS las migraciones en orden. 001 vuelve a
-- definir join_organization_by_code con la versión antigua y esta migración la
-- redefine después con `create or replace`, así que siempre gana esta.

alter table public.organizations
    add column if not exists join_code_expires_at timestamptz;

alter table public.organizations
    alter column join_code_expires_at set default (now() + interval '7 days');

-- Códigos existentes (sin caducidad): empiezan a contar desde que se aplica la
-- migración. En re-aplicaciones no toca nada (ya no quedan NULL).
update public.organizations
   set join_code_expires_at = now() + interval '7 days'
 where join_code_expires_at is null;

create or replace function public.join_organization_by_code(input_code text)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    target_org uuid;
    expires_at timestamptz;
begin
    if auth.uid() is null then
        raise exception 'authenticated user required';
    end if;

    select o.id, o.join_code_expires_at into target_org, expires_at
    from public.organizations o
    where lower(o.join_code) = lower(input_code)
    limit 1;

    if target_org is null then
        raise exception 'invalid join code';
    end if;

    if expires_at is null or expires_at <= now() then
        raise exception 'expired join code';
    end if;

    -- Entra como viewer. Si ya era miembro, conserva su rol (no se degrada ni se sube).
    insert into public.memberships (org_id, user_id, role)
    values (target_org, auth.uid(), 'viewer')
    on conflict (org_id, user_id) do nothing;

    return target_org;
end;
$$;
-- Sin `grant`: `create or replace` conserva los privilegios que ya tenga la función
-- (031 puede haberlos recortado para la Data API; el backend la llama como postgres).
