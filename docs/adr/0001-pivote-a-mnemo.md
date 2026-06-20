# ADR 0001 — Pivote de SmartErrorDebugger a Mnemo

**Fecha:** 2026-06-20
**Estado:** Aceptado

## Contexto

El proyecto nació como **SmartErrorDebugger**: un sistema RAG (DeepSeek-R1 local, ChromaDB+BM25, reranking, RAGAS) al que el usuario **pegaba una traza de error** para obtener un diagnóstico. Una auditoría profunda (`doc/AUDITORIA_CONCURSO_MTP.md`) y un análisis de posicionamiento concluyeron que ese enfoque tiene **poca utilidad real**:

- La mayoría de los errores de automatización son triviales y locales; pegar la traza en otra app y esperar 1-3 min es más trabajo que arreglarlo.
- Para errores no triviales, el dev ya pega en ChatGPT/Copilot (gratis, instantáneo, en su flujo).
- Una herramienta "a la que vas" pierde frente a "inteligencia que viene a ti".

El valor real no es **depurar un error**, sino **la pérdida de conocimiento de QA** en una consultora multi-cliente (MTP): conocimiento tribal que se evapora con la rotación, re-diagnóstico del mismo root cause entre equipos, flaky tests recurrentes.

## Decisión

Reposicionar el producto como **Mnemo — memoria de QA privada y federada para consultoras**. "Depurar" pasa a ser **una función**, no el producto. El núcleo de valor:

1. **Defect DNA** — huella + agrupación de fallos en familias con linaje cross-proyecto.
2. **Assurance Autopilot** — veredicto de aseguramiento por run (known/novel + riesgo + narrativa).
3. **Privacidad on-premise** — LLM/embeddings locales; el dato del cliente nunca sale (el foso para enterprise/regulados).

## Por qué evolución y no reescritura

La arquitectura ya construida **es el cimiento correcto**: el multitenant con Postgres+pgvector+aislamiento, la sanitización para compartir conocimiento, el LLM local y el structured output. Reescribir tiraría justo el foso y lo más lento. El cambio fue una **evolución del modelo de datos** (añadir entidades de run/fallo/familia de defecto) + nuevas capas de ingesta y veredicto, **sobre la misma base**.

## Consecuencias

- **Reutilizado:** multitenant (`tenant_kb`, RLS), auth Supabase (`security`), sanitizer, embeddings/LLM locales, `structured_analyzer`, FastAPI `/v2`, shell de frontend Next.js.
- **Nuevo:** `src/ingest/` (parsers Allure/JUnit), `src/defects/` (fingerprint, match, centroid, repository, ingestion_service, embedder), `src/assurance/` (verdict, narrator), endpoints `/v2/ingest/report`, `/v2/defects`, `/v2/defects/{id}`, `/v2/assurance/run/{id}`, migración `002_assurance.sql`, páginas frontend Assurance + Defect DNA.
- **Legacy en coexistencia (deuda):** el camino RAG single-tenant original (`ui.py` Streamlit, `vector_store.py` Chroma, `BugAnalyzer`, endpoints `/analyze` y `/sync` en `api.py`) sigue presente. Se retira `app_legacy.py` (código muerto). El resto se mantiene hasta que el camino Mnemo lo sustituya por completo; su poda requiere refactorizar `api.py` y se deja para un incremento posterior.
- **Aislamiento:** se confirmó que el rol del pooler de Supabase hace **BYPASS de RLS**, por lo que el aislamiento se hace con **filtros de membership en la capa de aplicación** (defensa real) y `FORCE RLS` queda como red de seguridad futura. Ver `docs/technical/modelo-datos.md`.
