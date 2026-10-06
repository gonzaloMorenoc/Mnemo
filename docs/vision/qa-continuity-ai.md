# Mnemo · QA Memory — visión y roadmap

**Fecha:** 2026-06-27 (actualizado en octubre de 2026) · **Estado:** marco adoptado; desde agosto el eje es la **continuidad del conocimiento** (que lo que sabe quien rota se quede en el proyecto).

## La promesa

> **Si mañana entra una persona nueva al proyecto, puede entender el producto, generar un plan de pruebas fiable y automatizar los escenarios principales con ayuda de IA, usando el conocimiento real acumulado del equipo.**

Mnemo deja de definirse como «el Autopilot que firma la release» y pasa a ser **la memoria operativa de QA del proyecto**: convierte el conocimiento disperso en **planes, escenarios y automatización que se pueden ejecutar**. El Autopilot (ingesta del CI → triaje → acción → acta firmada) **no desaparece**: es una de las **fuentes** que alimentan la memoria.

## El problema que resuelve

Una persona sénior conoce el sistema → se va, rota o está de vacaciones → el conocimiento queda disperso (Jira, Confluence, Git, Xray, Postman, transcripciones, Slack, tests antiguos, bugs cerrados, logs) → quien llega no sabe **qué** probar ni **por qué** → se repiten errores, se pierden reglas de negocio y baja la calidad.

El problema real no es *encontrar* información: es **convertirla en decisiones de testing** — qué probar, por qué, con qué datos, en qué entorno, qué riesgos hay, qué ya está automatizado, qué falta y cómo automatizarlo.

## Qué es (y qué no es)

**No es** un chatbot de la documentación. **Es un RAG operativo para QA**: recupera el conocimiento del proyecto y lo transforma en planes, casos y automatización, con una persona aprobando cada paso crítico. Cuatro capacidades:

1. **Memoria del proyecto** — captura y organiza el conocimiento de QA (reglas, flujos, riesgos, glosario, lecciones, retos) y el que ya genera el Autopilot (fallos, patrones, bugs).
2. **Onboarding** — un «modo persona nueva» que explica flujos, términos y riesgos históricos, y propone una ruta de aprendizaje.
3. **Plan de pruebas** — dada una historia y sus criterios: contexto, sistemas afectados, riesgos, datos, casos (positivos, negativos, límite), niveles (API, E2E, datos) y huecos de cobertura.
4. **Automatización** — del plan aprobado a Gherkin y Playwright **con el estilo del repositorio**, en un PR que nunca se mergea solo.

## Principios (no negociables)

- **La IA propone, una persona aprueba.** Planes y tests son propuestas; el PR nunca se mergea solo. Es el mismo invariante que el resto del producto: determinismo donde se firma, IA donde se multiplica. El LLM asiste, pero no decide ni firma.
- **Citar siempre la fuente y el nivel de confianza** (confirmado o inferido). Detectar conocimiento contradictorio u obsoleto es un objetivo pendiente (G6); hoy el estado `obsoleto` se marca a mano.
- **Aprender el estilo del repositorio** antes de generar código (estructura, nombres, page objects, fixtures, etiquetas, CI). No se genera desde cero.
- **Datos bajo control.** Embeddings siempre locales; LLM intercambiable y opcional (sin él, todo degrada a la vía determinista). Un proveedor local (Ollama) mantiene el dato dentro; uno externo exige activarlo de forma explícita (`ALLOW_EXTERNAL_LLM`). Cada organización tiene sus datos aislados. La demo pública usa un proveedor externo (`openai/gpt-oss-120b` en Groq).

## Arquitectura conceptual

```
Fuentes del proyecto (Jira/Confluence/Git/Xray/Slack/OpenAPI/tests/bugs/logs/CI)
        ↓ ingesta + normalización + clasificación (con confianza + fuente)
RAG (pgvector) + grafo de conocimiento (relaciones en Postgres)
        ↓
Memoria semántica del proyecto
        ↓
Agentes: onboarding · plan de pruebas · riesgos · huecos de cobertura · automatización
        ↓
Planes / casos Gherkin / código / consultas de validación / PRs / informes
```

Lo diferencial es **RAG más grafo de conocimiento**. El grafo (HU → afecta → servicio → publica → evento → consume → sistema → validado por → test → cubre → regla; bug → ocurrió en → flujo) permite preguntas que un RAG plano no responde («¿qué pruebas se ven afectadas si cambio la dirección fiscal?», «¿qué regla no tiene cobertura?»).

## Qué se reutiliza de Mnemo

| Capacidad | En Mnemo | Estado |
|---|---|---|
| Backend, RAG, vectores, LLM | FastAPI · pgvector · `LocalEmbedder` · `generate_structured` (LLM intercambiable, degrada) · `nl_query` | Stack propio y ligero sobre pgvector. De LangChain solo se usan dos conectores (`langchain-huggingface` para los embeddings y `langchain-ollama` para el proveedor local); no hay cadenas ni base vectorial aparte |
| Memoria semántica (captura y consumo) | Tabla `qa_knowledge` (`src/knowledge/`) | **Entregado** (Fase 1) |
| Ingesta de fuentes | Runs y tests del CI ✓ · bugs de Jira (`src/jira`) ✓ · tests del repositorio (`src/repo_ingest`) ✓ · Confluence por secciones ✓ | Faltan OpenAPI/Postman y transcripciones |
| Grafo de conocimiento | Defect DNA (familias y linaje) + grafo derivado en Postgres (`src/graph/`) | Entregado en su versión básica; falta el grafo rico (G4) |
| Agentes (onboarding, plan, riesgos, huecos) | `generate_structured` + la memoria + Jira | Entregados |
| Automatización (Gherkin → Playwright → PR) | `ai_repair.propose` + Self-heal + `github_app.open_draft_pr` + reporter | Entregada |
| Aislamiento entre clientes, auth | Filtro por pertenencia en cada consulta + RLS, auth de Supabase | Reutilizado |

## Modelo de datos objetivo (se construye por fases)

```
Project ├─ Domain ├─ BusinessRule · Flow · Risk · GlossaryTerm
        ├─ Requirement ├─ UserStory · AcceptanceCriteria · OpenQuestion
        ├─ TestAsset ├─ ManualTest · AutomatedTest · APIValidation · DataValidation
        ├─ Defect ├─ Bug · Incident · Regression
        └─ AutomationArtifact ├─ FeatureFile · StepDefinition · PageObject · Query
```
Relaciones: `BusinessRule —covered_by→ test`, `—affected_by→ UserStory`, `—source→ Jira`, `—risk→ nivel`. La Fase 1 lo modela de forma simple (tabla `qa_knowledge` con un `kind` flexible y su embedding); el grafo de relaciones es la Fase 2.

## Roadmap por fases

- **Fase 1 — Memoria, RAG operativo y plan de pruebas** ✅ **Entregada**
  - **1a (cimiento):** tabla `qa_knowledge` (7 tipos de producto: reglas, flujos, riesgos, glosario, lecciones, retos y patrones, vinculables a familias y runs; más 4 de oficio en la migración `027`), captura, y búsqueda y asistente unificados con el Defect DNA (`search_unified`). Módulo `src/knowledge/`, migración `018`.
  - **1b:** **plan de pruebas** — dada una HU (URL de Jira, PDF/Word o texto): contexto, sistemas, riesgos, datos y casos por nivel, citando el conocimiento. Exporta a Markdown o importa en Jira-Xray. Módulos `src/testplan/` y `src/xray/`, migración `019`.
- **Fase 2 — Grafo de conocimiento y detector de huecos** ✅ **Entregada**
  - Grafo de relaciones derivado en Postgres (`src/graph/`) y detector de huecos de cobertura (`/v2/graph/gaps`). Página `/app/graph`.
- **Automatización y onboarding** ✅ **Entregados**
  - **Automatización:** caso del plan → `.spec.ts` de Playwright con el estilo del repositorio → draft PR (GitHub App, nunca auto-merge). Módulo `src/automation/`.
  - **Onboarding:** «modo persona nueva» — ¿qué sabe el proyecto sobre X? —, ruta de aprendizaje y preguntas. Módulo `src/onboarding/`. Página `/app/onboarding`.
- **Ingesta del repositorio y huecos reales (G1+G2)** ✅ **Entregados**
  - Indexación de los tests del repositorio del cliente vía GitHub App (`src/repo_ingest/`, tabla `test_assets`, migración `020`) y detector de huecos que cruza memoria y tests reales por embeddings. Los ejemplos de estilo que usa la automatización salen de estos tests.
- **Continuidad del conocimiento** ✅ **Entregada (agosto)** — el eje actual:
  - **Memoria recuperable en español:** embeddings multilingües (`paraphrase-multilingual-MiniLM-L12-v2`); la razón que el equipo escribe al etiquetar una familia se guarda, se muestra y se busca por su propio vector (migración `030`).
  - **El oficio del proyecto:** tipos `runbook`, `dato_prueba`, `contacto` y `decision` (migración `027`).
  - **Captura sin clics:** propuestas de conocimiento tras cada ingesta del CI (bandeja con aprobación humana) e importación de Confluence por secciones.
  - **Índice de continuidad por proyecto y acta de traspaso firmada** (`mnemo.traspaso.v2`: firma también quién se va, quién llega y la huella del contenido), verificable sin cuenta (`src/continuity/`, migración `028`). Página `/app/continuity`.

**Pendiente:**
- **Ingesta de más fuentes (G3):** Confluence ✅; quedan OpenAPI/Postman y transcripciones, con clasificación automática, nivel de confianza y fuente citada.
- **Preguntar desde donde se trabaja:** MCP o Slack, para consultar la memoria sin abrir la web.
- **Grafo rico (G4):** servicio, evento, flujo e HU como nodos de primera clase, con relaciones tipadas.
- **Contradicción y obsolescencia (G6):** detectar conocimiento que se contradice entre fuentes o que ha quedado obsoleto.

Funciones transversales ya disponibles: *modo persona nueva* (onboarding), *¿qué sabe el proyecto?* (memoria y grafo), *plan y automatización con aprobación* (plan de pruebas y automatización) y *tests con el estilo del repositorio*.

## Riesgos y gobierno

| Riesgo | Mitigación |
|---|---|
| Conocimiento de baja calidad → respuestas malas | Citar fuentes; confianza (confirmado/inferido); revisión humana |
| Información obsoleta o contradictoria | Fecha de última actualización; reingesta; detección de contradicciones; aviso |
| Tests o planes frágiles | Plan → aprobación → generación; aprender el estilo del repositorio; ejecutar el test; PR sin auto-merge |
| Información sensible | Permisos por rol; no indexar secretos; redactar tokens; auditoría; despliegue en la infraestructura del cliente |
| **Ambición y alcance** | Disciplina de fases: empezar por memoria y plan, no por automatización |

## Posicionamiento

*«Convierte la memoria del proyecto en cobertura de QA que se puede ejecutar.»* No sustituye al QA: **conserva la memoria de QA del proyecto y acelera a cualquier persona nueva.** Comprador ideal: una consultora o empresa de QA externalizado de tamaño medio, que rota personal y sirve a clientes regulados; encaja con la arquitectura multicliente y de memoria.

## Estado

Las Fases 1 y 2, la automatización, el onboarding, la ingesta del repositorio con huecos reales (G1+G2) y la continuidad del conocimiento están en producción (`main`), con todas las migraciones de `db/migrations/` aplicadas. Lo siguiente: el resto de G3 (OpenAPI) y el grafo rico (G4).
