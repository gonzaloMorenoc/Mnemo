# QA Continuity AI — Roadmap de cierre de gaps

**Fecha:** 2026-06-28 · **Actualizado:** 2026-07-16 (G1 y G2 entregados) · **Parte de:** [QA Continuity AI](qa-continuity-ai.md)

## Propósito

Mnemo ya entrega el **núcleo** de la visión QA Continuity AI: las 4 capacidades + el foso (Knowledge Graph + Coverage Gap), end-to-end, con "IA propone / humano aprueba", citación de fuentes y on-prem. Un análisis frente a la propuesta completa de la idea sitúa la cobertura en **~70%**: está todo el concepto, no toda la *amplitud*. Este documento prioriza el **30% restante** para alcanzar la visión completa.

Cada fase de cierre (G1…G6), cuando se aborde, pasa por el flujo del proyecto: **brainstorming → spec → plan → subagentes → review → PR**. Este doc es el mapa, no el spec de ninguna.

## Lo que ya está (no se replantea)
Memoria (`qa_knowledge` + `search_unified`), Test Plan Agent, Onboarding Agent, Automation Agent (→ draft PR), Knowledge Graph derivado + Coverage Gap; **ingesta del repo del cliente** (`src/repo_ingest/`, tabla `test_assets`, migración 020) con **gap de cobertura real** (memoria × tests del repo) y estilo few-shot desde los assets; multitenancy RLS, config cifrada por org, embeddings locales + LLM intercambiable, GitHub App (`open_pr_with_new_file`, `read_file`, `list_tree`), integraciones Jira/Xray, ingesta de reportes CI (7 formatos) + Jira + PDF/Word/texto.

## Los gaps (del análisis) → fases de cierre

| # | Gap | Estado |
|---|---|---|
| G1 | **Ingesta del repositorio** (tests + código existentes) | ✅ **entregado** — `POST /v2/repo/index` indexa los tests del repo (vía GitHub App) como `test_assets` con embeddings; cotas de 200 ficheros / 100 KB |
| G2 | **Coverage Gap real** (reglas/HU sin test del repo) | ✅ **entregado** — `src/graph/gaps.py` cruza `qa_knowledge` × `test_assets` por similitud de embeddings |
| G3 | **Ingesta multi-fuente** (Confluence, OpenAPI, transcripciones, Postman…) | ⚠️ solo Jira + ficheros + reportes CI |
| G4 | **Knowledge Graph rico** (servicio/evento/flujo/HU como nodos) | ⚠️ grafo derivado simple (knowledge/defect/domain) |
| G5 | **Automation+** (API/contract/SQL, ejecutar antes del PR) | ⚠️ parcial — el estilo ya sale de los assets reales del repo (G1); solo Playwright, sin ejecutar/compilar |
| G6 | **Frescura** (contradicciones, obsolescencia, reingesta periódica) | ⚠️ hay `last_seen`/`confidence`; falta detección + jobs |

---

## Detalle por fase

### G1 · Ingesta del repositorio — ✅ ENTREGADO
Implementado en `src/repo_ingest/` (migración `020_test_assets.sql`): `POST /v2/repo/index` lee el repo de la org vía la GitHub App (`list_tree`/`read_file`), filtra los tests, detecta framework y dominio, y los indexa como `test_assets` con embeddings (cotas: 200 ficheros / 100 KB por fichero). `GET /v2/repo/tests` los lista. Alcance no cubierto (queda para G5/G4): perfil de estilo explícito más allá del few-shot y la relación test↔regla tipada.

### G2 · Coverage Gap real — ✅ ENTREGADO
`src/graph/gaps.py` cruza `qa_knowledge` × `test_assets` por similitud de embeddings: el detector señala "esta regla/flujo no tiene test real del repo" además de los huecos de conocimiento.

### G3 · Ingesta multi-fuente de conocimiento
- **Objetivo:** el "Project Memory Ingestor" más allá de Jira/ficheros. **Orden sugerido dentro de la fase:** Confluence (la config `CONFLUENCE_URL` ya existe) → OpenAPI/Swagger (define servicios/endpoints, alimenta G4) → transcripciones (texto) → Postman.
- **Incluye:** un conector por fuente con **clasificación** (`type`/`domain`/`source`/`confidence`) → `qa_knowledge`; config cifrada por org (patrón Jira/GitHub).
- **Desbloquea:** más memoria → mejores planes/onboarding; OpenAPI alimenta G4.
- **Depende de:** nada (paralelizable con G1). **Reusa:** patrón de integraciones cifradas, `resolve_hu`/ingest, `qa_knowledge`.
- **Esfuerzo:** M por fuente (incremental). · **Riesgo:** calidad/ruido de cada fuente → la clasificación + `confidence` lo mitigan.

### G4 · Knowledge Graph rico
- **Objetivo:** modelar entidades de 1ª clase (**sistema/servicio, evento, flujo, HU**) + relaciones tipadas (**afecta / publica / consume / valida**) — el grafo del documento, no el derivado.
- **Incluye:** tabla de nodos/edges tipados (o `qa_knowledge` + tabla de `edges` con RLS); poblado desde OpenAPI (servicios/endpoints, G3), el código (servicios), las HU (Jira) y los tests (G1).
- **Desbloquea:** las preguntas potentes ("¿qué tests se ven afectados si cambio X?", "¿qué consume este evento?") y planes con **impacto** real.
- **Depende de:** G1 (tests) + G3 (OpenAPI/servicios). **Reusa:** `src/graph` (de derivado → modelado).
- **Esfuerzo:** L · **Riesgo:** el más alto — modelado + poblado fiable; empezar por un dominio piloto.

### G5 · Automation+ — parcial (el estilo del repo ya está)
- **Ya cubierto:** `src/automation/style.py` recupera los `test_assets` más similares como ejemplos few-shot → el estilo sale del repo real, no de un sample pegado.
- **Pendiente:** generar más allá de Playwright (**API/contract tests, SQL/Data validations**) y **ejecutar/compilar** el test antes del PR.
- **Reusa:** `src/automation`, `GitHubCodeHost`.
- **Esfuerzo:** L · **Riesgo:** ejecutar tests requiere entorno (out-of-scope inicial: limitarse a compilar/parsear).

### G6 · Frescura del conocimiento
- **Objetivo:** detección de **contradicciones** (dos fuentes que se contradicen → marcar para confirmación), aviso de **obsolescencia** (por `last_seen`), y **reingesta periódica** (jobs).
- **Depende de:** las fuentes (G1/G3). **Reusa:** `qa_knowledge` (`last_seen`/`confidence`), un scheduler (cron/worker).
- **Esfuerzo:** M · **Riesgo:** bajo; transversal, mejor al final.

> **Modelo de datos rico** (TestAsset / AutomationArtifact / Requirement como entidades): NO es una fase suelta — emerge de G1 (test assets) y G4 (entidades del grafo). Se construye al hacerlas.

---

## Secuencia recomendada (viva, tras entregar G1+G2)

```
G1 ✅ ── G2 ✅
G3 (multi-fuente) ──► G4 (grafo rico) ◄── [tests de G1 ya disponibles]
G5 (automation+, el resto)
G6 (frescura)  [transversal, al final]
```

1. **G3** — empezar por **Confluence** (la config `CONFLUENCE_URL` ya existe) y **OpenAPI** (alimenta G4); incremental, una fuente por PR.
2. **G4 (grafo rico)** — G1 ya aporta los tests; cuando G3 aporte OpenAPI/servicios, pilotar con un dominio.
3. **G5 (resto de automation+)** — API/contract/SQL + compilar antes del PR.
4. **G6 (frescura)** — transversal, al final, cuando haya varias fuentes que puedan contradecirse o envejecer.

## Prioridad de un vistazo
| Fase | Valor | Esfuerzo | Desbloquea | Estado |
|---|---|---|---|---|
| **G1** Ingesta repo | 🟢 Alto | M-L | G2, G4, G5 | ✅ entregado |
| **G2** Gap real | 🟢 Alto | S-M | estrella "Knowledge Gap" | ✅ entregado |
| **G3** Multi-fuente | 🟡 Medio-Alto | M/fuente | G4 | **siguiente** |
| **G4** Grafo rico | 🟢 Alto | L | preguntas de impacto | tras G3 |
| **G5** Automation+ | 🟡 Medio | L | cobertura real de código | parcial (estilo ✅) |
| **G6** Frescura | 🟡 Medio | M | confianza a largo plazo | final |

> ⚠️ Antes de invertir en este roadmap conviene cerrar el checkpoint de la **base 11 (IP)** del concurso — es ortogonal al código pero condiciona la estrategia.
