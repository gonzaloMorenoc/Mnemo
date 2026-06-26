# Legacy — SmartErrorDebugger (producto anterior)

Este directorio conserva artefactos del **producto anterior** de Mnemo: un asistente RAG
de depuración de errores ("SmartErrorDebugger"). El producto actual es **Mnemo Autopilot**
(ingeniero de QA autónomo: triaje → acción Nivel 2 → Release Assurance Certificate + gate),
cuyo código vive en `src/api_v2.py` + `src/triage/`, `src/actions/`, `src/certify/`, `src/defects/`.

## Estado de la convivencia (a 2026-06-26)
- `api.py` (raíz) es el FastAPI **legacy** (monta `BugAnalyzer`/`qa_chain` RAG) y **además**
  monta el router del Autopilot (`v2_router`). Los módulos RAG (`src/loader.py`,
  `src/vector_store.py`, `src/model.py`, `src/evaluator.py`, `src/history.py`,
  `src/inspector.py`, `src/retriever.py`) los usa `api.py`.
- `src/structured_analyzer.py` (análisis RAG estructurado) lo consume `src/api_v2.py` por un
  endpoint heredado; se reutilizará para la causa-raíz multimodal (Bloque B).

## Archivado aquí
- `DEMO.md` — guion de demo del flujo RAG anterior (no del Autopilot).
- `seed_demo.py` — seed del flujo anterior.

## Follow-up (no en este PR)
Extraer un entrypoint limpio del Autopilot (un `app` que monte solo `v2_router`) y mover los
módulos RAG a `legacy/` una vez `api.py` deje de ser el host del Autopilot. Es un esfuerzo
aparte (toca despliegue/Docker), no un cambio de higiene.
