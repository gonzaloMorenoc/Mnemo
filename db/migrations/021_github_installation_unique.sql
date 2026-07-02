-- 021: un installation_id de GitHub pertenece a una sola organización.
--
-- Mitiga el confused-deputy (hallazgo N-C1): sin esto, un admin de cualquier org
-- podía vincular el installation_id de OTRO cliente y lograr que Mnemo leyera/
-- escribiera en su repo privado. Este índice impide que dos organizaciones
-- reclamen la misma instalación. La verificación de propiedad (la cuenta de la
-- instalación == dueño del repo) se hace además en la capa de API al vincular
-- (src/api_v2.py::_verify_installation_ownership).
--
-- Nota: el fix completo (probar que quien vincula controla la instalación vía el
-- setup-redirect de la GitHub App con state firmado) queda como seguimiento.

create unique index if not exists org_integrations_github_installation_unique
    on public.org_integrations (installation_id)
    where provider = 'github' and installation_id is not null;
