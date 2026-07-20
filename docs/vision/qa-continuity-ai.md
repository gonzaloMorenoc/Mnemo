# QA Memory — Visión y roadmap

**Fecha:** 2026-06-27 · **Estado:** marco adoptado (Mnemo evoluciona a QA Memory; se construye sobre el repo actual). · **Origen:** idea del usuario tras la [revisión profunda](../auditoria/2026-06-27-revision-profunda/00-sintesis.md).

## La promesa

> **Si mañana entra una persona nueva al proyecto, puede entender el producto, generar un plan de pruebas fiable y automatizar los escenarios principales con ayuda de IA, usando el conocimiento real acumulado del equipo.**

Mnemo deja de definirse como "el Autopilot que firma el release" y pasa a ser **la plataforma de memoria operativa de QA**: convierte el conocimiento disperso de un proyecto en **planes, escenarios y automatización accionables**. El Autopilot (ingesta CI → triaje → acción → certificado) **no desaparece**: se convierte en una de las **fuentes** que alimentan la memoria.

## El problema que resuelve

Una persona senior conoce el sistema → se va / rota / está de vacaciones → el conocimiento queda disperso (Jira, Confluence, Git, Xray, Postman, transcripciones, Slack, tests antiguos, bugs cerrados, logs) → la persona nueva no sabe **qué** probar ni **por qué** → se repiten errores, se pierden reglas de negocio, baja la calidad.

El problema real no es *encontrar* información: es **convertirla en decisiones de testing** — qué probar, por qué, con qué datos, en qué entorno, qué riesgos hay, qué ya está automatizado, qué falta, cómo automatizarlo.

## Qué es (y qué no es)

**No es** un "chatbot de la documentación". **Es un RAG operacional para QA**: una IA que recupera el conocimiento del proyecto y lo transforma en planes, casos y automatización, con el humano aprobando cada paso crítico. Cuatro capacidades:

1. **Memoria inteligente del proyecto** — captura y organiza el conocimiento de QA (reglas, flujos, riesgos, glosario, lecciones, retos) + el conocimiento que ya genera el Autopilot (fallos, patrones, bugs).
2. **Asistente de onboarding QA** — "modo persona nueva": explica flujos, términos, riesgos históricos, y genera rutas de aprendizaje.
3. **Generador de planes de prueba** — dada una historia/criterios: contexto, sistemas afectados, riesgos, datos, casos (positivos/negativos/límite), niveles (API/E2E/datos), gaps de cobertura.
4. **Generador/automatizador de tests** — del plan aprobado: Gherkin → Playwright/API **siguiendo el estilo del repo** → PR (nunca auto-merge).

## Principios (no negociables)

- **La IA propone, el humano aprueba.** Planes y tests son propuestas; el PR nunca se mergea solo. (Coherente con el invariante "determinismo donde firmo, IA donde multiplico"; el LLM local *asiste*, no decide ni firma — esto elimina el problema de "perfección" del certificado.)
- **Citar siempre la fuente + nivel de confianza** (confirmado vs inferido). Detectar conocimiento contradictorio/obsoleto.
- **Aprende el estilo del repo** antes de generar código (estructura, naming, page objects, fixtures, tags, CI). No genera desde cero.
- **Privado / on-premise.** LLM y embeddings locales; el dato del cliente no sale; multi-tenant con aislamiento por organización. (Diferenciador real para clientes regulados.)

## Arquitectura conceptual

```
Fuentes del proyecto (Jira/Confluence/Git/Xray/Slack/OpenAPI/tests/bugs/logs/CI)
        ↓ ingesta + normalización + clasificación (con confianza + fuente)
RAG (pgvector) + Knowledge Graph (relaciones en Postgres)
        ↓
Memoria semántica del proyecto QA
        ↓
Agentes: Onboarding · Test Plan · Risk · Coverage Gap · Automation
        ↓
Planes / casos Gherkin / código / queries de validación / PRs / reportes
```

La clave diferencial: **RAG + grafo de conocimiento**. El grafo (HU → afecta → servicio → publica → evento → consume → sistema → validado por → test → cubre → regla; bug → ocurrió en → flujo) permite preguntas que un RAG plano no puede ("¿qué pruebas se ven afectadas si cambio la dirección fiscal?", "¿qué regla no tiene cobertura?").

## Mapeo con Mnemo (qué se reusa — ~60-70% ya existe)

| Capacidad QA Memory | En Mnemo hoy | Acción |
|---|---|---|
| Backend / RAG / vector / LLM local | FastAPI · pgvector · `LocalEmbedder` · `generate_structured` (Ollama, degrada) · `nl_query` | Reusar (stack ligero propio; sin LangChain/Qdrant) |
| Memoria semántica (captura+consumo) | — (nueva entidad `qa_knowledge`) | **Fase 1** (K1+K2 ya especificado) |
| Ingesta de fuentes | CI runs/tests ✓ · Jira bugs (`src/jira`) ✓ · tests del repo Git (`src/repo_ingest`) ✓ | Ampliar a historias/criterios/Confluence/OpenAPI |
| Knowledge Graph | Defect DNA (familias + linaje) = grafo embrionario | Extender (relaciones en Postgres) |
| Agentes (onboarding/plan/risk/gap) | `generate_structured` + el conocimiento + Jira | Nuevos |
| Automation Agent (Gherkin→Playwright→PR) | `ai_repair.propose` + self-heal + `github_app.open_draft_pr` + reporter | Ampliar (ya abre PRs con código) |
| Multitenancy / RLS / auth / on-prem | ✓ ya (auditado y endurecido) | Reusar |

## Modelo de datos objetivo (se construye por fases)

```
Project ├─ Domain ├─ BusinessRule · Flow · Risk · GlossaryTerm
        ├─ Requirement ├─ UserStory · AcceptanceCriteria · OpenQuestion
        ├─ TestAsset ├─ ManualTest · AutomatedTest · APIValidation · DataValidation
        ├─ Defect ├─ Bug · Incident · Regression
        └─ AutomationArtifact ├─ FeatureFile · StepDefinition · PageObject · Query
```
Relacionado: `BusinessRule —covered_by→ test`, `—affected_by→ UserStory`, `—source→ Jira`, `—risk→ nivel`. La Fase 1 modela esto de forma simple (entidad `qa_knowledge` con `kind` flexible + embedding); el grafo de relaciones es la Fase 2.

## Roadmap por fases

- **Fase 1 — Memoria + RAG operacional + Test Plan** ✅ **Entregado (main)**
  - **1a (cimiento):** entidad `qa_knowledge` (7 kinds: reglas/flujos/riesgos/glosario/lecciones/retos/patrones, vinculable a familias/runs) + captura + búsqueda/asistente unificados con el Defect DNA (`search_unified`). Módulo `src/knowledge/`, migración `018`.
  - **1b:** **Test Plan Agent** — dada una HU (URL Jira / PDF-Word / texto): contexto, sistemas, riesgos, datos, casos por nivel, citando el conocimiento. Exportar Markdown / importar a Jira-Xray. Módulo `src/testplan/` + `src/xray/`, migración `019`.
- **Fase 2 — Knowledge Graph + Coverage Gap Detector** ✅ **Entregado (main)**
  - Grafo de relaciones derivado en Postgres (`src/graph/`) + detector de huecos de cobertura (`/v2/graph/gaps`). Página `/app/graph`.
- **Automation Agent + Onboarding Agent** ✅ **Entregado (main)**
  - **Automation Agent:** caso del plan → código Playwright `.spec.ts` al estilo del repo → draft PR (GitHub App, nunca auto-merge). Módulo `src/automation/`.
  - **Onboarding Agent:** "modo persona nueva" — ¿qué sabe el proyecto sobre X? + ruta de aprendizaje + chat. Módulo `src/onboarding/`. Página `/app/onboarding`.
- **Ingesta del repo + Coverage Gap real (G1+G2)** ✅ **Entregado (main)**
  - Indexación de los tests del repo del cliente vía GitHub App (`src/repo_ingest/`, tabla `test_assets`, migración `020`) y detector de gaps que cruza memoria × tests reales por embeddings. El estilo few-shot del Automation Agent sale de estos assets.

**Pendiente (roadmap real — detalle en [qa-continuity-gaps-roadmap.md](qa-continuity-gaps-roadmap.md)):**
- **Ingesta multi-fuente más allá de Jira/Git (G3):** Confluence, OpenAPI/Postman, transcripciones, con clasificación automática, nivel de confianza y fuente citada.
- **Knowledge Graph rico (G4):** servicio/evento/flujo/HU como nodos de primera clase con relaciones tipadas.
- **Detección de contradicción/obsolescencia (G6):** identificar conocimiento que se contradice entre fuentes o que ha quedado obsoleto.

Funcionalidades estrella (transversales, ya disponibles): *modo persona nueva* (onboarding), *¿qué sabe el proyecto?* (knowledge + graph), *generar plan + automatización con aprobación* (test-plan + automation), *test automation al estilo del repo*.

## Riesgos y gobierno

| Riesgo | Mitigación |
|---|---|
| Conocimiento de baja calidad → respuestas malas | Citar fuentes; confianza (confirmado/inferido); feedback humano |
| Información obsoleta/contradictoria | Fecha de última actualización; reingesta; detección de contradicciones; aviso |
| Tests/planes frágiles | Plan→aprueba→genera; aprender el estilo del repo; ejecutar el test; PR sin auto-merge |
| Información sensible | Permisos por rol; no indexar secretos; redactar tokens; auditoría; on-prem |
| **Ambición/alcance** | Disciplina de fases: empezar por memoria+plan, no por automatización |
| **IP (base 11 del concurso)** | Construir en Mnemo conserva la opción de forkear; leer la base 11 antes de monetizar/presentar |

## Posicionamiento

*"Convierte la memoria del proyecto en cobertura QA accionable."* No sustituye al QA: **conserva la memoria de QA del proyecto y acelera a cualquier persona nueva.** Comprador ideal (de la revisión profunda): consultora/outsourcer de QA mediano que rota personal y sirve clientes regulados — fit nativo con la arquitectura multi-tenant, on-prem y de memoria.

## Estado

Las Fases 1 y 2, el Automation Agent, el Onboarding Agent y la ingesta del repo con gap real (G1+G2) están todos en producción (`main`), con las migraciones de `db/migrations/` aplicadas al completo. El siguiente paso es la **ingesta multi-fuente** (G3: Confluence, OpenAPI) y después el grafo rico (G4) — ver [qa-continuity-gaps-roadmap.md](qa-continuity-gaps-roadmap.md).
