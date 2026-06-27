# Mnemo — Visión funcional

## Qué es

**Mnemo** es la **memoria de QA** de una consultora: una plataforma **privada y on-premise** que convierte los fallos dispersos de los runs de test en **conocimiento reutilizable** y en **veredictos de aseguramiento** automáticos.

El nombre viene de *Mnemosyne*, la personificación de la memoria. La idea central: una organización de QA **olvida lo que ya aprendió** — el conocimiento de por qué falló algo y cómo se resolvió vive en la cabeza de un sénior y se evapora cuando rota de proyecto. Mnemo lo retiene, lo agrupa y lo pone donde el equipo trabaja.


## Propuesta de valor

- **Privado por diseño**: LLM y embeddings 100% locales (Ollama + HuggingFace). Las trazas y logs de los clientes **nunca salen** a una nube externa. Coste de API = 0 €. Diferenciador real frente a herramientas cloud para clientes enterprise bajo NDA/GDPR/LGPD.
- **Conocimiento federado**: cada organización/cliente tiene su base aislada (scopes `org`/`user`/`global`); el conocimiento puede compartirse al acervo `global` **sanitizado**.
- **Defect DNA**: cada fallo recibe una huella (fingerprint) y se agrupa en **familias de defecto**; el mismo defecto se reconoce **a través de proyectos y en el tiempo** (linaje), aunque cambien líneas, UUIDs o timestamps.
- **Assurance Autopilot**: por cada run de test, un **veredicto** automático — cuántos fallos son conocidos vs nuevos, señal de riesgo, familias recurrentes y una narrativa generada por LLM (que degrada con elegancia si el LLM no está).

## Personas

| Persona | Qué busca en Mnemo |
|---|---|
| **QA / Test Automation Engineer** | Saber, ante un run, qué fallos son **nuevos** y cuáles ya **conocidos** (con su contexto/fix), sin re-diagnosticar desde cero. |
| **Delivery / QA Manager** | Salud de calidad por proyecto, **defectos recurrentes** (Defect DNA) y veredictos de aseguramiento para informes al cliente. |

## Casos de uso (slice actual)

1. **Ingesta de un run** — subir un reporte **Allure** (JSON) o **JUnit** (XML) de un proyecto → Mnemo extrae los fallos, los **sanitiza**, calcula su **fingerprint** y los **agrupa** en familias.
2. **Veredicto de aseguramiento** — por cada run, cuántos fallos conocidos vs nuevos, señal de riesgo (`atención`/`ok`), familias recurrentes top y narrativa LLM.
3. **Defect DNA** — dashboard de familias de defecto con ocurrencias y **linaje entre proyectos** de la organización.

## Guion de demo (2-3 min)

Una org "MTP" con varios proyectos (clientes). Se ingieren reportes; un *timeout* aparece en dos proyectos → el dashboard de **Defect DNA** muestra esa familia con su linaje cross-proyecto; un run nuevo trae un fallo novedoso → el **veredicto** lo marca como nuevo y la señal de riesgo pasa a `atención`.

## Aislamiento multi-cliente (alcance)

El slice actual modela **una org (la consultora) con varios `project`** (clientes). Las familias son `org`-scoped y abarcan proyectos → muestra "el mismo defecto en varios proyectos". El federado **cross-organización** (scope `global` sanitizado entre orgs distintas) es el siguiente paso del roadmap.

## Estado y roadmap

- **Hecho (backend + frontend):** ingesta Allure/JUnit, fingerprint, matching en familias, persistencia (Postgres+pgvector con aislamiento), endpoints `/v2`, veredicto de aseguramiento, y las páginas **Assurance** + **Defect DNA**.
- **Roadmap:** webhook de CI en vivo, más conectores (Jira/GitHub), conocimiento `global` cross-cliente, packaging air-gapped como appliance para sectores regulados, generación de tests dirigida por defectos.
