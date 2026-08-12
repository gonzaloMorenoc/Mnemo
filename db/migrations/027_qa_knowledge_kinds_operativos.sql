-- Kinds operativos: sitio para el OFICIO del proyecto (auditoría 12-ago, H3).
--
-- Los 7 kinds originales hablan del producto y de sus fallos. Lo que de verdad se va
-- cuando se va el QA senior no tenía dónde vivir: cómo se levanta el entorno
-- (runbook), con qué usuarios y datos se prueba (dato_prueba), qué equipo lleva cada
-- pieza (contacto, por ROL — nunca una persona) y qué se acordó con el cliente,
-- sobre todo lo que se decidió NO probar (decision).
--
-- Aditiva: el set nuevo es superconjunto del anterior, así que ninguna fila existente
-- viola el CHECK nuevo y no hace falta migrar datos.
--
-- Se recrean los DOS checks. El de knowledge_proposals es imprescindible: el refine
-- enumera KINDS al LLM (src/knowledge/proposal_service.py) y escribe el kind devuelto
-- en la propuesta, así que sin este ALTER proponer 'runbook' daría CheckViolation y
-- el endpoint de refine respondería 502.
--
-- `if exists` porque scripts/docker_init.py re-aplica todas las migraciones en cada
-- arranque: la migración tiene que poder ejecutarse dos veces sin romper.

alter table public.qa_knowledge drop constraint if exists qa_knowledge_kind_check;
alter table public.qa_knowledge add constraint qa_knowledge_kind_check
    check (kind in ('regla_negocio','flujo','riesgo','glosario','leccion','reto','patron',
                    'runbook','dato_prueba','contacto','decision'));

alter table public.knowledge_proposals drop constraint if exists knowledge_proposals_kind_check;
alter table public.knowledge_proposals add constraint knowledge_proposals_kind_check
    check (kind in ('regla_negocio','flujo','riesgo','glosario','leccion','reto','patron',
                    'runbook','dato_prueba','contacto','decision'));
