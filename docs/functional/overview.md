# Mnemo — QA Continuity AI: visión funcional

## Qué es

**Mnemo** es la **plataforma de continuidad operativa de QA** de una consultora: un sistema **privado y on-premise** que convierte el conocimiento disperso de un proyecto (reglas de negocio, flujos, bugs, tests, runs de CI) en **planes de prueba, automatización y memoria accionable**.

El nombre viene de *Mnemosyne*, la personificación de la memoria. La idea central: una organización de QA **olvida lo que ya aprendió** — el conocimiento de por qué falló algo, qué reglas de negocio son críticas o cómo se probó un flujo vive en la cabeza de un sénior y se evapora cuando rota de proyecto. Mnemo lo retiene, lo organiza y lo pone donde el equipo trabaja.

> **La IA propone, el humano aprueba.** Planes, casos y PRs son propuestas. Nunca hay auto-merge.

## Propuesta de valor

- **Privado por diseño:** embeddings siempre locales y LLM intercambiable — en modo on-premise (Ollama `qwen3:8b`, el default de código) las trazas y logs de los clientes nunca salen a una nube externa y el coste de API es 0 €. Diferenciador real frente a herramientas cloud para clientes enterprise bajo NDA/GDPR/LGPD. Un proveedor cloud (Gemini/Groq/OpenAI-compatible) es opcional y exige opt-in explícito (`ALLOW_EXTERNAL_LLM=true`); es lo que usa la demo pública.
- **Conocimiento federado multi-tenant:** cada organización/cliente tiene su base aislada (RLS + `org_id`); el conocimiento puede compartirse al acervo `global` sanitizado.
- **RAG operacional, no chatbot:** recupera el conocimiento del proyecto y lo transforma en planes, casos y automatización — con fuente y nivel de confianza citados.
- **Cita siempre la fuente:** confirmado vs. inferido; detecta conocimiento contradictorio u obsoleto.

## Personas

| Persona | Qué busca en Mnemo |
|---|---|
| **QA / Test Automation Engineer** | Generar un plan de pruebas desde una HU sin partir de cero; saber qué huecos de cobertura hay; automatizar con el estilo del repo. |
| **Persona nueva en el proyecto** | Entender flujos, términos y riesgos históricos rápidamente; tener una ruta de aprendizaje guiada. |
| **Delivery / QA Manager** | Salud de calidad por proyecto, defectos recurrentes (Defect DNA), cobertura actualizada e informes de aseguramiento para el cliente. |

## Cinco capacidades (todas en producción)

### 1. Memoria del proyecto (`/app/knowledge`)

Captura y organiza el conocimiento de QA del proyecto en 7 tipos: reglas de negocio, flujos, riesgos, glosario, lecciones aprendidas, retos abiertos y patrones. La búsqueda semántica unificada (`search_unified`) cruza la memoria con el **Defect DNA** (familias de defecto, fingerprints, linaje entre proyectos) producido por el Autopilot. Módulo: `src/knowledge/`, tabla `qa_knowledge`. Endpoints: `/v2/knowledge/*`.

### 2. Test Plan Agent (`/app/test-plan`)

Dada una historia de usuario — como URL de Jira, PDF/Word o texto libre — genera un plan de pruebas completo: contexto, sistemas afectados, riesgos, datos de prueba, casos por nivel (API/E2E/datos), positivos/negativos/límite. Cita la memoria del proyecto. Salida exportable como Markdown o importable directamente a Jira-Xray (integración nativa). Módulo: `src/testplan/` + `src/xray/`. Endpoints: `/v2/test-plan/*`.

### 3. Onboarding Agent (`/app/onboarding`)

"Modo persona nueva": responde ¿qué sabe el proyecto sobre X?, genera una ruta de aprendizaje personalizada y mantiene un chat guiado apoyado en la memoria del proyecto. Módulo: `src/onboarding/`. Endpoints: `/v2/onboarding/domain-summary` y `/v2/onboarding/learning-path`; el chat usa `/v2/knowledge/ask`.

### 4. Automation Agent (botón en `/app/test-plan`)

A partir de un caso del plan aprobado, genera código Playwright `.spec.ts` aprendiendo el estilo del repositorio (naming, fixtures, page objects, tags). Abre un draft PR vía GitHub App para revisión humana — nunca auto-merge. Módulo: `src/automation/` + `src/ci/github_app.py`. Endpoints: `/v2/automation/*`.

### 5. Knowledge Graph + Coverage Gap (`/app/graph`)

Grafo de relaciones derivado del conocimiento y los tests (HU → servicio → test → regla → bug). Detector de huecos de cobertura: qué reglas o flujos no tienen tests que los cubran. Módulo: `src/graph/`. Endpoints: `/v2/graph` + `/v2/graph/gaps`.

## El Autopilot como fuente

El **Autopilot** (ingesta CI → triaje automático → certificado firmado → self-heal) no desaparece: se convierte en una de las fuentes que alimentan la memoria. Aporta:

- **Ingesta de runs** (webhook `POST /v2/ci/webhook`, HMAC; o upload de reportes con autodetección de 7 formatos: JUnit, TestNG, Robot Framework, Allure, Playwright, Cypress, Cucumber) → fallos sanitizados con fingerprint.
- **Defect DNA**: familias de defecto con linaje cross-proyecto.
- **Veredicto de aseguramiento**: por run — conocidos vs. nuevos, señal de riesgo, narrativa LLM.
- **Self-heal**: propone PR de mantenimiento cuando detecta un locator roto con confianza suficiente.

## Casos de uso actuales

1. **Capturar conocimiento** — subir una regla, flujo o lección al knowledge base del proyecto.
2. **Preguntar al proyecto** — búsqueda semántica unificada sobre memoria + Defect DNA.
3. **Generar plan de pruebas** — desde HU/criterios de aceptación, citando la memoria.
4. **Onboarding de persona nueva** — ruta de aprendizaje + chat sobre el proyecto.
5. **Detectar huecos de cobertura** — qué reglas o flujos no tienen tests.
6. **Automatizar un caso** — del plan aprobado al draft PR con código Playwright.
7. **Ingerir run de CI** — veredicto de aseguramiento + actualización de Defect DNA.

## Aislamiento multi-cliente

Cada organización/cliente tiene su base aislada (RLS + `org_id`). Las familias de defecto son `org`-scoped. El conocimiento puede compartirse al acervo `global` sanitizado entre proyectos de la misma org.

## Estado

Todas las capacidades descritas están en producción (`main`), con las migraciones de `db/migrations/` aplicadas al completo. Ver roadmap y próximos pasos en [`docs/vision/qa-continuity-ai.md`](../vision/qa-continuity-ai.md).
