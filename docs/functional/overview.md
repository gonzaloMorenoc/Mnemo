# Mnemo — visión funcional

## Qué es

**Mnemo** es la memoria del proyecto de QA que se queda cuando las personas rotan. El
nombre viene de *Mnemosyne*, la personificación de la memoria.

El problema: en una consultora de QA, el conocimiento que hace insustituible a un perfil
sénior —por qué falló algo, qué reglas de negocio son críticas, cómo se levanta el
entorno, a quién se pregunta— vive en su cabeza y se evapora cuando cambia de proyecto. El
que llega lo reconstruye a base de preguntar, si quien se fue sigue contestando.

Mnemo lo retiene sin pedir una sesión de documentación que nadie hace: se alimenta del
trabajo diario (los runs del CI y lo que el equipo escribe al etiquetar un fallo), lo
organiza por proyecto, mide cuánto se sabe de cada uno y lo devuelve a quien llega, con la
fuente citada.

> **La IA propone, una persona aprueba.** Las propuestas de conocimiento, los planes, los
> casos y los PRs pasan por una aprobación humana. Nunca hay auto-merge.

## Personas

| Persona | Qué busca en Mnemo |
|---|---|
| **Responsable de la consultora / Delivery** | Ver qué proyectos dependen de una sola persona antes de que rote, y entregar al cliente un acta de que el conocimiento quedó depositado. |
| **QA que llega a un proyecto** | Entender el proyecto la primera semana sin depender de quien se fue: entorno, datos de prueba, contactos, decisiones, y por qué cada fallo recurrente es lo que es. |
| **QA del proyecto** | Que el triaje de los runs no le robe la mañana, y que lo que explica al etiquetar un fallo sirva a otros. |

## Capacidades

### 1. Continuidad (`/app/continuity`)

**Índice de continuidad por proyecto** (0-100): media ponderada de cuatro dimensiones,
cada una con su recuento a la vista — memoria de defectos, el porqué de las etiquetas,
oficio del proyecto y reglas con respaldo. Es un recuento recalculable: el mismo estado da
siempre el mismo número, y sin datos dice «sin datos», no un 0.

**Acta de traspaso firmada** (rol owner/admin): congela el índice y su desglose en un
documento firmado con Ed25519 que se verifica en la página pública `/verify`, sin cuenta.
Es lo que la consultora entrega cuando rota a una persona. Módulo: `src/continuity/`.

### 2. Memoria del proyecto (`/app/knowledge`)

Conocimiento de QA en 11 tipos: los del **producto** (reglas de negocio, flujos, riesgos,
glosario, lecciones, retos, patrones) y los del **oficio** (runbooks, datos de prueba,
contactos, decisiones). La búsqueda semántica unificada cruza la memoria con el Defect
DNA, incluida la razón que el equipo escribió al etiquetar cada familia. Llega por tres
vías: a mano, importada de Confluence (troceada por secciones) y **propuesta por la IA
tras cada ingesta**, en una bandeja donde una persona aprueba o descarta. Módulo:
`src/knowledge/`.

### 3. Onboarding (`/app/onboarding`)

Para quien llega: resumen de un dominio, ruta de aprendizaje y preguntas a la memoria en
lenguaje natural, con citas. Sin LLM, la pregunta devuelve las fuentes relevantes en vez
de una respuesta redactada. Módulo: `src/onboarding/`.

### 4. El lazo del CI: Autopilot (`/app/autopilot`)

Es la fuente que mantiene viva la memoria:

- **Ingesta** por webhook (`POST /v2/ci/webhook`, firmado con HMAC) o subida de informes
  con autodetección de 7 formatos (JUnit, TestNG, Robot Framework, Allure, Playwright,
  Cypress, Cucumber), más issues de Jira.
- **Defect DNA**: cada fallo se agrupa en una familia de defecto con su historia y su
  linaje entre proyectos.
- **Triaje determinista**: cada fallo sale como real, inestable, de entorno o de
  mantenimiento, con la regla que lo decidió. El LLM solo desempata lo ambiguo.
- **Acta del run** firmada y verificable, y gate en el PR.
- **Self-heal**: ante un selector roto, propone el parche; con aprobación, abre un draft PR.

### 5. Calibración (`/app/calibration`)

Cada etiqueta humana mide al motor contra su propia predicción independiente, por
cliente. Esa precisión decide si un run limpio puede firmarse como `apto` o se queda en
`apto-con-reservas`.

### 6. Plan de pruebas y automatización (`/app/test-plan`)

De una historia de usuario (texto, URL de Jira o PDF/Word) a un plan de pruebas manual o
Gherkin que cita la memoria, exportable a Jira-Xray; y de un caso aprobado a un `.spec.ts`
de Playwright con el estilo del repositorio del cliente, en un draft PR. Módulos:
`src/testplan/`, `src/xray/`, `src/automation/`.

### 7. Grafo y huecos de cobertura (`/app/graph`)

Relaciones entre el conocimiento y los tests, y huecos: reglas sin test, defectos sin
conocimiento, dominios sin lección, riesgos sin mitigación. Módulo: `src/graph/`.

## Casos de uso

1. **Una persona rota de proyecto** — revisar el índice, completar lo que falta y emitir el acta de traspaso.
2. **Llega alguien nuevo** — preguntar a la memoria y seguir la ruta de aprendizaje.
3. **Llega un run del CI** — triaje, acta y, si hay fallos nuevos, propuestas de conocimiento.
4. **Etiquetar un fallo** — la razón escrita queda buscable para el siguiente.
5. **Capturar el oficio** — runbooks, datos de prueba, contactos y decisiones del proyecto.
6. **Planificar y automatizar** — de la HU al plan, y del caso al draft PR.
7. **Detectar huecos** — qué reglas o flujos no tienen tests.

## Aislamiento multi-cliente

Cada organización (cliente) tiene sus datos aislados: las tablas de datos del cliente llevan `org_id`,
con RLS en la base de datos y filtros por pertenencia en cada consulta del backend.

## Estado

Las capacidades descritas están en `main` y desplegadas en la demo. Visión y roadmap:
[`docs/vision/qa-continuity-ai.md`](../vision/qa-continuity-ai.md).
