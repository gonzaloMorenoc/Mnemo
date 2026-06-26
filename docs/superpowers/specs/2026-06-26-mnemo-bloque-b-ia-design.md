# Mnemo — Bloque B: la IA como protagonista (diseño maestro)

**Fecha:** 2026-06-26 · **Origen:** análisis de vendibilidad/IA (`docs/auditoria/2026-06-26-sintesis-vendibilidad-ia.md` §3 + `analisis-ia/02-ia-llm-foco.md`) · **Rama base de la 1ª apuesta:** `feat/mnemo-ai-selfeval` (desde `main` f93afef)

## Objetivo

Subir el **techo de IA** de Mnemo sin tocar el **piso determinista**: pasar de "determinismo con LLM mínimo" a un agente con IA generativa defendible, para ganar el AI Innovation Award (MTP, 30-oct-2026) y justificar valoración de producto. Cinco apuestas, un PR cada una.

## Principio rector (invariante de todo el bloque)

> **Determinismo donde firmo; IA donde multiplico.** La separación es por riesgo de la decisión: ¿se firma / bloquea un deploy / modifica el repo sin humano?
> - **Sí** (veredicto del certificado, gate) → **determinista, auditable** (intacto de #27). La IA, como mucho, *propone*; el humano *aprueba*.
> - **No** (informa, propone, explora) → **IA generativa**. El coste de un error es "el humano lo descarta", no "firmé una mentira".

Las 5 apuestas viven en el lado "No" (o como señal opcional firmada que **degrada** el veredicto, nunca lo infla).

## Decisiones (confirmadas)

- **LLM híbrido:** Ollama **local por defecto** (mantiene "coste API 0€ / on-premise", el diferenciador del pitch); Claude **opt-in** vía `ALLOW_EXTERNAL_LLM` (calidad enterprise). La infra (`src/llm/factory.py`) ya lo soporta.
- **Alcance:** las **5 apuestas** (1 self_eval-judge, 2 causa-raíz, 3 NL-DNA, 4 reparación AST, 5 orquestador).
- **Causa-raíz (2):** versión **rica sobre texto** (DOM+trace+stack+diff+linaje) ahora; **visión (screenshots)** = follow-up (requiere ingerir imágenes en el reporter+ingesta).
- **Medición:** golden sets + LLM-judge/RAGAS + ECE + evals-en-CI, integrada con las apuestas (empieza en B1).
- `DATABASE_URL`=prod; main protegida (PR por fase); determinismo del certificado/gate intacto; TDD por subagentes; commits con la línea `Claude-Session`.

## Arquitectura común — `src/ai/` (capa de generación)

Un módulo nuevo `src/ai/` con un **helper de generación estructurada** que todas las apuestas reusan:
- **`generate_structured(*, prompt, context, schema, provider=None) -> dict`**: construye el prompt con el `context` (RAG), invoca `provider` (default `get_llm_provider()` — Ollama local o Claude opt-in), parsea/valida el JSON contra `schema`, y **degrada a un fallback determinista** si el LLM falla, no está, o devuelve basura (patrón ya probado en `structured_analyzer`/`tiebreaker`/`explainer`).
- **`citations`**: el helper exige que la salida cite los ids de evidencia usados (para faithfulness medible).
- `structured_analyzer.py` se refactoriza para usar este helper + el provider híbrido (hoy usa `OllamaLLM` directo).
- **Invariante:** este helper NUNCA se llama en el camino que se firma/bloquea sin aprobación humana.

---

## PR-B1 — `self_eval` con LLM-judge + base de generación + medición

**Qué:** la base `src/ai/` (arriba) + un **LLM-judge** (estilo RAGAS: faithfulness/groundedness/answer-relevance) que puntúa las salidas LLM-asistidas, y su score entra **firmado** en el `self_eval` del certificado (extiende el `compute_self_eval` determinista de #27, no lo reemplaza).
- `self_eval` gana un sub-bloque `ai_eval` **opcional**: `{method:"llm_judge", judge_model, faithfulness, groundedness, n, evaluated_at}`. Si no hay LLM (Ollama caído / sin opt-in), `ai_eval: null` y el `self_eval` determinista se mantiene (degradación elegante).
- **El score bajo degrada** el veredicto (apto→apto-con-reservas), nunca lo infla — coherente con #27 (`confidence` ya modula).
- **Medición:** golden sets (triaje/heal/causa-raíz como datasets versionados) + un **eval-en-CI** que corre los golden sets y **falla el build** si la precisión de IA cae de un umbral. ECE para calibrar el `confidence`.

**Toca:** `src/ai/` (nuevo), `src/certify/certificate.py` + `service.py` (inyectar `ai_eval`), `tests/` (golden sets + judge), CI (`.github/workflows/`).

## PR-B2 — Causa-raíz rica anclada al Defect DNA

**Qué:** evolucionar `src/structured_analyzer.py` de "texto→JSON" a un análisis de causa-raíz que recibe **DOM + trace + stack + diff del commit + casos análogos del Defect DNA (RAG) + linaje cross-proyecto** y emite root-cause estructurado **con citas**. Usa la base `src/ai/` (provider híbrido). Se cablea al **ticket enriquecido** (la acción `ticket`/`quarantine`).
- El **diff del commit**: si no se ingiere hoy, obtenerlo on-demand (GitHub compare API por el `commit_sha`) o degradar sin él.
- **Visión (screenshot):** follow-up (requiere ingesta de imágenes).

**Toca:** `src/structured_analyzer.py`, `src/ai/`, `src/actions/ticket.py` (consumir el análisis), `src/defects/` (recuperar análogos+linaje), tests + golden set de causa-raíz.

## PR-B3 — NL sobre el Defect DNA (backend)

**Qué:** endpoint `POST /v2/defects/ask` — RAG conversacional sobre el vector store (defects/certificados/acciones): pregunta → embed (HF, ya existe) → recuperar top-K del tenant (pgvector) → el LLM responde con **evidencia citada y linaje**. Multitenant (membership-gated). Híbrido.
- **UI del chat:** fuera de este PR (va en el Bloque C / demo, o un PR de frontend aparte).

**Toca:** `src/defects/repository.py` (búsqueda semántica para Q&A), `src/ai/`, `src/api_v2.py` (endpoint), `src/multitenant_models.py` (request/response), tests.

## PR-B4 — Reparación LLM+AST más allá del locator

**Qué:** cuando el self-heal determinista no aplica (no es un locator roto: un `expect` desfasado, un `sleep` frágil, un dato de fixture obsoleto), un actuator propone un parche **sobre el AST de TypeScript (ts-morph)**, lo **valida ejecutando el test**, y abre PR borrador + humano. Nunca toca el camino firmado.
- **Riesgo técnico (señalado):** requiere un **runner Node** (ts-morph + ejecutar el test) — decidir dónde corre (subproceso Node / sandbox). Si el riesgo aprieta para oct, simplificar (p. ej. proponer el parche sin ejecutar, marcándolo "no validado") o recortar.

**Toca:** `src/actions/selfheal/` (nuevo actuator AST), un runner Node (`packages/` o script), `src/ai/`, tests.

## PR-B5 — Agente orquestador

**Qué:** un loop que, por run, encadena causa-raíz (B2) → reparación (B4) → consulta al DNA (B3), se **auto-evalúa con B1**, y propone el lote de cambios **bajo aprobación**. Es la materialización de "inteligencia que viene a ti".
- **Encuadre honesto para oct-2026:** se demuestra como **orquestación de B1-B4 sobre el repo de demo controlado**, no como autonomía total en cualquier codebase.

**Toca:** `src/ai/` (orquestador), `src/actions/service.py` (integración), tests.

---

## Medición (transversal, empieza en B1)

- **Golden sets** versionados: triaje (4 categorías + ambiguos), self-heal (DOM verde/roto → locator correcto), causa-raíz (root-cause de referencia de un sénior). El lazo de calibración (F5a, `triage_corrections`) ya acumula el de triaje — cosecharlo.
- **RAGAS / LLM-judge:** faithfulness, groundedness, answer-relevance sobre causa-raíz, NL y reparación.
- **ECE** (Expected Calibration Error): valida/corrige el cap de confianza 0.70 del tiebreaker con evidencia.
- **Evals-en-CI:** cada cambio de prompt/modelo corre los golden sets; si la precisión cae de un umbral, **falla el build** ("Mnemo se aplica su propia medicina de Assurance").

## Orden de ejecución

**B1 → B2 → B3 → B4 → B5.** B1 primero (base de generación + judge + medición = credibilidad de lo demás). Cada PR: writing-plans + subagent-driven + review final + PR, como las tandas. **Dependencia:** B2-B5 usan la base `src/ai/` de B1 → conviene mergear B1 antes de arrancar B2 (o apilar).

## Fuera de alcance (otros bloques / follow-ups)

- **Bloque C** (demo 3 actos e2e + ROI en pantalla + PDF del cert + aislamiento en vivo + UI del chat NL) y **Bloque D** (pitch/categoría).
- **Visión multimodal** (ingerir screenshots + LLM con visión) — follow-up de B2.
- **Fine-tuning/distilación por tenant** — foso futuro, ya pavimentado por el lazo.
