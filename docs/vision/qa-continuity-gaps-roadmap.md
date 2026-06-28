# QA Continuity AI — Roadmap de cierre de gaps

**Fecha:** 2026-06-28 · **Parte de:** [QA Continuity AI](qa-continuity-ai.md)

## Propósito

Mnemo ya entrega el **núcleo** de la visión QA Continuity AI: las 4 capacidades + el foso (Knowledge Graph + Coverage Gap), end-to-end, con "IA propone / humano aprueba", citación de fuentes y on-prem. Un análisis frente a la propuesta completa de la idea sitúa la cobertura en **~70%**: está todo el concepto, no toda la *amplitud*. Este documento prioriza el **30% restante** para alcanzar la visión completa.

Cada fase de cierre (G1…G6), cuando se aborde, pasa por el flujo del proyecto: **brainstorming → spec → plan → subagentes → review → PR**. Este doc es el mapa, no el spec de ninguna.

## Lo que ya está (no se replantea)
Memoria (`qa_knowledge` + `search_unified`), Test Plan Agent, Onboarding Agent, Automation Agent (→ draft PR), Knowledge Graph derivado + Coverage Gap; multitenancy RLS, config cifrada por org, LLM/embeddings locales, GitHub App (`open_pr_with_new_file`, `read_file`), integraciones Jira/Xray, ingesta de reportes CI + Jira + PDF/Word/texto.

## Los gaps (del análisis) → fases de cierre

| # | Gap | Estado hoy |
|---|---|---|
| G1 | **Ingesta del repositorio** (tests + código existentes) | ❌ no se lee el repo del cliente |
| G2 | **Coverage Gap real** (reglas/HU sin test del repo) | ⚠️ hoy mide huecos sobre la memoria, no sobre tests reales |
| G3 | **Ingesta multi-fuente** (Confluence, OpenAPI, transcripciones, Postman…) | ⚠️ solo Jira + ficheros + reportes CI |
| G4 | **Knowledge Graph rico** (servicio/evento/flujo/HU como nodos) | ⚠️ grafo derivado simple (knowledge/defect/domain) |
| G5 | **Automation+** (API/contract/SQL, page objects del repo, ejecutar) | ⚠️ solo Playwright `.spec.ts`, estilo vía sample pegado |
| G6 | **Frescura** (contradicciones, obsolescencia, reingesta periódica) | ⚠️ hay `last_seen`/`confidence`; falta detección + jobs |

---

## Detalle por fase

### G1 · Ingesta del repositorio — *el desbloqueador clave*
- **Objetivo:** leer el repo del cliente (vía la GitHub App ya configurada por org) para indexar los **tests existentes** (`.feature`/`.spec.ts`/API) y capturar el **estilo** (estructura de carpetas, naming, page objects, fixtures, tags).
- **Incluye:** `list_tree`/`read_file` sobre el repo (extender `GitHubCodeHost`); extractor que clasifica los tests → `qa_knowledge` (nuevo kind, p. ej. `test_existente`) con su `domain`/relación a reglas; un "perfil de estilo" del repo.
- **Desbloquea:** G2 (gap real), G5 (Automation "from project style" de verdad) y enriquece G4 (test↔regla↔dominio). **Es el de mayor efecto palanca.**
- **Depende de:** GitHub App por org (✅ existe). **Reusa:** `GitHubCodeHost`, `qa_knowledge`, `search_unified`, `LocalEmbedder`.
- **Esfuerzo:** M-L · **Riesgo:** repos grandes → filtrado/cotas; variedad de frameworks.

### G2 · Coverage Gap real — *quick win sobre G1*
- **Objetivo:** que el detector pase de "huecos de conocimiento" a "**esta regla/HU/dominio no tiene test real**", cruzando `qa_knowledge` × tests ingeridos (G1).
- **Desbloquea:** la funcionalidad estrella "Knowledge Gap Detector" del documento de idea.
- **Depende de:** G1. **Reusa:** `src/graph/gaps.py` (extender con un nuevo kind de gap).
- **Esfuerzo:** S-M · **Riesgo:** bajo. **Alto valor / bajo coste una vez hecho G1.**

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

### G5 · Automation+
- **Objetivo:** el Automation Agent genera más allá de Playwright: **API/contract tests, SQL/Data validations**, reutiliza **page objects/fixtures reales** del repo (G1), y opcionalmente **ejecuta/compila** el test antes del PR.
- **Depende de:** G1 (estilo + assets del repo). **Reusa:** `src/automation`, `GitHubCodeHost`.
- **Esfuerzo:** L · **Riesgo:** ejecutar tests requiere entorno (out-of-scope inicial: limitarse a compilar/parsear).

### G6 · Frescura del conocimiento
- **Objetivo:** detección de **contradicciones** (dos fuentes que se contradicen → marcar para confirmación), aviso de **obsolescencia** (por `last_seen`), y **reingesta periódica** (jobs).
- **Depende de:** las fuentes (G1/G3). **Reusa:** `qa_knowledge` (`last_seen`/`confidence`), un scheduler (cron/worker).
- **Esfuerzo:** M · **Riesgo:** bajo; transversal, mejor al final.

> **Modelo de datos rico** (TestAsset / AutomationArtifact / Requirement como entidades): NO es una fase suelta — emerge de G1 (test assets) y G4 (entidades del grafo). Se construye al hacerlas.

---

## Secuencia recomendada

```
G1 (ingesta repo) ─┬─► G2 (gap real)        [quick win, alto valor]
                   ├─► G5 (automation+)
                   └─► G4 (grafo rico) ◄─┐
G3 (multi-fuente) ──────────────────────┘
                                         G6 (frescura)  [transversal, al final]
```

1. **G1 + G2 primero** — el mayor salto de valor con la reusa más alta: convierten "estilo vía sample" en "estilo del repo" y "gap de conocimiento" en "gap de cobertura real" (la funcionalidad estrella). G2 es casi gratis tras G1.
2. **G3 en paralelo** — empezar por **Confluence** (config ya presente) y **OpenAPI** (alimenta G4); incremental, una fuente por PR.
3. **G4 (grafo rico)** — cuando G1 (tests) y G3 (OpenAPI/servicios) den con qué poblarlo; pilotar con un dominio.
4. **G5 (automation+)** — sobre el estilo/assets del repo de G1.
5. **G6 (frescura)** — transversal, al final, cuando haya varias fuentes que puedan contradecirse o envejecer.

## Prioridad de un vistazo
| Fase | Valor | Esfuerzo | Desbloquea | Cuándo |
|---|---|---|---|---|
| **G1** Ingesta repo | 🟢 Alto | M-L | G2, G4, G5 | **Ahora** |
| **G2** Gap real | 🟢 Alto | S-M | estrella "Knowledge Gap" | tras G1 |
| **G3** Multi-fuente | 🟡 Medio-Alto | M/fuente | G4 | paralelo |
| **G4** Grafo rico | 🟢 Alto | L | preguntas de impacto | tras G1+G3 |
| **G5** Automation+ | 🟡 Medio | L | cobertura real de código | tras G1 |
| **G6** Frescura | 🟡 Medio | M | confianza a largo plazo | final |

**Recomendación de arranque:** **G1**, y dentro de G1 acotar el MVP a *leer los tests existentes de un repo + perfil de estilo* (deja el código/PRs para después). Con eso, G2 y la mejora de G5 caen casi solas y se nota de inmediato en el producto.

> ⚠️ Antes de invertir en este roadmap conviene cerrar el checkpoint de la **base 11 (IP)** del concurso — es ortogonal al código pero condiciona la estrategia.
