# Auditoría de proyecto y plan para el MTP AI Innovation Award

**Proyecto:** SmartErrorDebugger (rama `redesign`)
**Fecha de auditoría:** 2026-06-19
**Plazo del concurso:** 30 de octubre de 2026 · Resolución: 27 de noviembre de 2026
**Método:** auditoría multi-agente del código real (núcleo RAG, multitenancy/seguridad, frontend/producto, testing/DevOps), contrastada con las bases del premio.

---

## 1. Veredicto en una frase

El proyecto tiene una **tesis ganadora** para este premio (sistema de IA para QA, **100% local/coste de API = 0 €**, multitenant, con auto-evaluación de calidad RAGAS), pero **hoy NO está en estado de ganar**: son en realidad **dos mitades desconectadas** —un backend RAG legacy que funciona a medias y una plataforma nueva (multitenant + frontend) de alta calidad pero **sin conectar**—, y un jurado técnico de **una empresa de testing** detectaría las costuras en minutos. La buena noticia: **el hueco es estrecho y de bajo esfuerzo** (la lógica ya existe; falta el puente HTTP), y hay **~4 meses** de margen.

---

## 2. ¿Encaja con las bases? — Sí, con fuerza conceptual

| Requisito de las bases | Encaje |
|---|---|
| Orientado a construir **sistemas de IA** | ✅ Sistema RAG completo (retrieval híbrido + rerank + LLM + evaluación) |
| **Nuevos paradigmas / enfoques innovadores** | 🟡 RAG híbrido + RAGAS continuo + KB federada por org; innovador en el *dominio QA*, no en lo fundamental |
| **Eficiencia de ejecución y optimización de costes** | 🟡 Coste de API = 0 € (excelente), pero la *ejecución* hoy es lenta (ver §4) |
| **Hardware específico / arquitecturas optimizadas** | 🟡 Todo on-premise (Ollama/LLM local); falta cuantificar y optimizar |
| **Escalabilidad** | 🟡 Diseño multitenant con pgvector+RLS bien planteado, sin probar |
| **MVP funcional lo más desarrollado posible** | 🔴 **Punto débil hoy**: el MVP nuevo no opera de extremo a extremo |

**Conclusión:** el encaje temático es de los mejores posibles para MTP (QA / Digital Business Assurance, multi-cliente, datos sensibles). El riesgo no es la idea, es el **estado de ejecución**.

---

## 3. Estimación de puntuación: hoy vs. potencial

Pesos oficiales y lectura realista del estado actual frente al alcanzable cerrando los gaps de este plan.

| Criterio | Peso | **Hoy** | **Potencial** | Palanca principal |
|---|---|---|---|---|
| Innovación | 20% | Medio | Medio-Alto | Narrativa "QA que se auto-evalúa + KB federada privada" |
| Eficiencia (coste y ejecución) | 20% | Medio | **Alto** | Coste 0 € ya; falta arreglar latencia (RAGAS async, indexado incremental) |
| Calidad técnica del MVP | 15% | **Bajo** | Alto | Conectar frontend↔backend; quitar red flags |
| Escalabilidad | 15% | Medio | Alto | Probar RLS + benchmark pgvector |
| Impacto y aplicabilidad | 15% | Medio-Alto | Alto | Demo e2e creíble para QA multi-cliente |
| Capacidad del equipo | 10% | — | — | Depende del dossier (ver §7) |
| Viabilidad económica | 5% | **Alto** | Alto | TCO ≈ 0 €/análisis, privado por diseño |

El proyecto **se juega el premio en pasar "Calidad del MVP" y "Eficiencia" de medio/bajo a alto**, que es exactamente donde están los gaps más baratos de cerrar.

---

## 4. Hallazgos clave de la auditoría

### 4.1. Fortalezas reales (a explotar en el pitch)
- **Coste de API = 0 € verificado.** Todo el pipeline (LLM, embeddings, reranker, evaluación) corre local vía Ollama/HuggingFace. Cero llamadas a OpenAI/Anthropic. **Privacidad por diseño**: los logs del cliente nunca salen de la infraestructura. Es el argumento más sólido y diferencial (Eficiencia 20% + Viabilidad 5% + Impacto 15%).
- **Arquitectura RAG seria** (no un "chatbot juguete"): búsqueda híbrida BM25 (0.4) + vectorial (0.6) para capturar tanto semántica como códigos de error exactos, + reranking Cross-Encoder BGE. La optimización de no re-ejecutar el reranker en generación es real (`api.py:64-73`).
- **RAGAS con 4 métricas** (faithfulness, relevancy, context precision/recall): habla literalmente el idioma "Assurance" de MTP. Es un diferenciador potente… cuando funcione (hoy roto, ver 4.2).
- **Diseño multitenant de buena factura** (`db/migrations/001_multitenant_kb.sql`): scopes org/user/global, invariantes por CHECK constraints, RLS por scope, índices (parciales, GIN, ivfflat). Mejor que muchos MVPs.
- **Frontend de alta calidad de ingeniería**: Next.js 16 App Router, React 19, TS estricto, shadcn/ui, TanStack Query, **auth Supabase real y funcional**, manejo de errores y estados limpio. Es el activo más pulido.

### 4.2. Show-stoppers / red flags (lo que hundiría la nota)

> Un jurado con expertos en QA y arquitectura clonará el repo. Esto es lo que encontraría.

1. **🔴 El MVP nuevo no funciona de extremo a extremo.** El frontend llama a `POST /api/v2/analyze`, `/v2/upload`, `/v2/orgs*` → el backend FastAPI real (`api.py`) **no tiene ninguna ruta `/v2/*`**. Pulsar "Analizar" devuelve 404. La lógica de negocio existe (`src/tenant_kb.py`, `src/structured_analyzer.py`, `src/multitenant_models.py`) pero **nadie la monta en un servidor HTTP**. Es una capa de servicio sin capa de transporte.
2. **🔴 `ImportError` al clonar.** `src/security.py` y `src/tenant_kb.py` importan `SUPABASE_JWKS_URL`, `DATABASE_URL`, `UPLOAD_DIR`, `DEFAULT_TOP_K`… que `src/config.py` **no define**. Además faltan deps (`psycopg`, `pyjwt`, `pgvector`) en `requirements.txt`. Esos módulos **ni siquiera importan** en un entorno limpio.
3. **🔴 `docker-compose up` no levanta el MVP que se presenta.** El compose solo arranca `ui.py` (Streamlit legacy). **No incluye la API ni el frontend Next.js**. El evaluador haría `docker-compose up`, abriría `:8501` y vería la UI vieja, no el producto del pitch. Además `volumes: .:/app` pisa las deps de la imagen.
4. **🔴 RAGAS devuelve 0% en silencio.** `evaluator.py:22` usa `OllamaEmbeddings("all-MiniLM-L6-v2")`, pero ese modelo **no existe en Ollama** → excepción → el `try/except` devuelve `{0,0,0,0}` sin avisar. La función estrella ("QA de la IA en tiempo real") muestra métricas en 0%.
5. **🟠 La base de conocimiento es ruido.** Los 105 JSON de `data/logs/` son artefactos Allure/Playwright (`uuid`, `status`, `steps`…) que **no encajan** con los campos que espera el loader (`error_message`/`stack_trace`); 39 son `status: skipped` sin trazas. El RAG recupera metadata irrelevante. Solo hay **1** log real.
6. **🟠 Sanitización con fugas.** `sanitizer.py` (la pieza que justifica "contribuir al KB global con confianza") **filtra 9 de 11** tipos de secreto comunes: JWT, claves AWS/GCP, tokens `ghp_`/`xoxb-`, tarjetas, claves PEM, teléfonos… Riesgo legal real (GDPR/LGPD) para datos de clientes de QA.
7. **🟠 RAGAS síncrono = latencia de 1-3 min por consulta.** Por cada `/analyze` se ejecutan 4 métricas RAGAS (3 son LLM-as-judge con el mismo DeepSeek-R1:8B). Contradice "eficiencia de ejecución".
8. **🟠 Testing de adorno.** Cobertura real **~13%**; el pipeline RAG (loader/retriever/vector_store/model) al **0%**. Los tests de evaluación son **mocks de formato**. **No hay CI para el backend Python** (solo para el frontend, y cubre 2 tests triviales). Para una empresa de testing, esto es lo primero que miran.
9. **🟡 Otros:** `requirements.txt` sin versiones pinneadas; `/health` estático (no comprueba Ollama/Chroma); `print()` en vez de `logging`; `README` con afirmaciones falsas ("Implemented against existing backend endpoints `/v2/orgs`…"); módulos huérfanos (`structured_analyzer.py` no se usa); `app_legacy.py` contradictorio (modelo `mistral`, chunks 1000/200).

---

## 5. Plan priorizado para ganar

Tres fases por orden de retorno. Esfuerzo: **S** < ½ día · **M** 1-3 días · **L** 1-2 semanas. El objetivo de la Fase 1 es **que el MVP funcione e2e y el repo no tenga red flags** (es lo que más nota mueve por menos esfuerzo).

### Fase 1 — "Que funcione y no avergüence" (semanas 1-2) · imprescindible
| # | Acción | Esf. | Criterios |
|---|---|---|---|
| 1 | **Montar el router `/v2` en FastAPI** que exponga la lógica ya escrita: `/v2/analyze` (vía `StructuredAnalyzer`), `/v2/upload`, `/v2/orgs*`, con `Depends(get_current_user)`. Cierra el gap frontend↔backend → **demo e2e login→analizar→resultado citado**. | M | MVP 15%, Impacto 15% |
| 2 | **Arreglar imports/deps**: añadir `DATABASE_URL`, `UPLOAD_DIR`, `DEFAULT_TOP_K`, `SUPABASE_*` a `config.py`; declarar `psycopg[binary,pool]`, `pgvector`, `pyjwt`; **pinnear** todas las versiones; commitear los módulos untracked. | S | MVP 15% |
| 3 | **Arreglar `docker-compose`** para levantar el stack real (API + frontend + Ollama + Postgres/pgvector), quitar `volumes: .:/app`, esperar health del modelo. `.env.example` completo. | M | MVP 15%, Escalab. 15% |
| 4 | **Arreglar RAGAS** (embeddings válidos: envolver el `HuggingFaceEmbeddings` local o usar `nomic-embed-text` en Ollama) y **sacarlo del camino crítico** (background task / endpoint on-demand). | S/M | Eficiencia 20%, MVP 15% |
| 5 | **Datos de demo creíbles**: poblar el KB con errores reales de QA/Selenium bien formados (o extender el loader para parsear Allure: `statusDetails.message`/`trace`). | S | MVP 15%, Impacto 15% |
| 6 | **Limpieza de red flags**: corregir `README` (quitar claims falsos), `/health` real (pingea Ollama/Chroma), `logging` en vez de `print`, borrar `app_legacy.py`. | S | MVP 15% |

### Fase 2 — "Que puntúe alto" (semanas 3-5)
| # | Acción | Esf. | Criterios |
|---|---|---|---|
| 7 | **Sanitización robusta** antes de contribución global: integrar `detect-secrets`/Presidio + patrones (JWT, claves cloud, tarjetas Luhn, IBAN, teléfonos ES/MX/BR) + tests de no-fuga. | M | Impacto 15%, Escalab. 15% |
| 8 | **Validar RLS de verdad**: `ALTER TABLE … FORCE ROW LEVEL SECURITY`, rol `authenticated` no-BYPASSRLS, y convertir `RLS_VALIDATION.md` en **suite pytest** (dos usuarios, casos negativos cross-tenant) en CI. "Demostramos que user_b no ve datos de org_alpha" es una frase ganadora. | M | Escalab. 15% |
| 9 | **CI backend Python** (espejo del de frontend): `pytest` + `ruff` + gate de cobertura. **Tests reales del pipeline RAG** (loader/retriever/vector_store con fixtures pequeñas, sin LLM). | M | MVP 15% |
| 10 | **Eficiencia medible**: indexado incremental con hash de contenido (no re-embeber todo), usar la función SQL `search_chunks_scoped` (1 query en vez de 3), `psycopg_pool`. **Benchmark** p50/p95 vs nº de chunks. | M/L | Eficiencia 20%, Escalab. 15% |

### Fase 3 — "Que destaque" (semanas 6-8, si hay margen)
| # | Acción | Esf. | Criterios |
|---|---|---|---|
| 11 | **Ángulo de innovación**: bucle de auto-mejora del KB (feedback real que reordena ranking — hoy `update_feedback` está roto), detección de patrones de errores recurrentes, e **integración CI/CD** (analizar fallos de pipelines automáticamente — GitHub Action). | L | Innovación 20% |
| 12 | **Routing de modelo por complejidad** (modelo ligero 3B para casos simples / juez RAGAS; 8B reasoning solo cuando aporta) → más eficiencia de ejecución. | M | Eficiencia 20% |
| 13 | **Cuantificación económica** para el dossier: coste/1000 análisis vs GPT-4, RAM/latencia, gráfico de TCO. | S | Viabilidad 5%, Eficiencia 20% |

---

## 6. La narrativa ganadora (cómo posicionarlo)

> **"Un copiloto de debugging para QA, 100% on-premise: cero coste de API, privacidad por diseño, conocimiento federado por cliente y auto-evaluación continua de su propia calidad."**

Ejes del pitch, alineados con los pesos:
1. **Privacidad + coste 0 € (Eficiencia 20% + Viabilidad 5%):** los logs de los clientes de MTP nunca salen a una nube externa; el coste marginal por análisis es ~0 €. Diferenciador frente a cualquier solución basada en GPT-4.
2. **"QA que se QA-evalúa" (Innovación 20% + encaje MTP):** RAGAS mide objetivamente si la IA alucina. Una herramienta de aseguramiento de calidad que asegura su propia calidad: meta-mensaje perfecto para Digital Business Assurance.
3. **Conocimiento federado por organización (Escalabilidad 15% + Impacto 15%):** cada equipo/cliente tiene su KB aislada (RLS), con opción de aportar conocimiento sanitizado al acervo global. Encaja con MTP multi-cliente en 3 países.
4. **Eficiencia de ejecución (Eficiencia 20%):** retrieval híbrido + rerank para precisión técnica; indexado incremental; modelo local dimensionado a hardware modesto.

---

## 7. Recomendaciones para la documentación a presentar (sección 5 de las bases)

- **a) Equipo (Capacidad 10%):** describir experiencia real en IA/QA/arquitectura. Si es un equipo pequeño, enfatizar la **amplitud del stack dominado** (RAG, multitenancy, pgvector/RLS, Next.js) como prueba de capacidad.
- **b) Proyecto:** problema (triaje de errores en QA multi-cliente), beneficios (tiempo de resolución, conocimiento que no se pierde, privacidad), plan de trabajo (este plan por fases), y **estimación de ingresos/costes** (TCO ≈ 0 € de API; potencial como producto interno MTP o SaaS para clientes).
- **c) Solución:** **MVP funcional operativo** (← Fase 1 es lo que lo hace real) + descripción técnica de la arquitectura (el diagrama + los diferenciadores). Incluir las **métricas RAGAS reales** y el **benchmark de eficiencia** como evidencia objetiva.

---

## 8. Riesgos y nota de elegibilidad

- **Elegibilidad:** el concurso está restringido a integrantes de MTP España/México/Brasil, LAUDE, LAUDE Canarias o APARA. Confirmar pertenencia antes de invertir esfuerzo.
- **Cesión de derechos (base 11):** participar cede a MTP los derechos de explotación de lo presentado. Valorar qué se enseña.
- **Honestidad técnica:** no presentar como "implementado" lo que es maqueta. Tras la Fase 1 ya no hace falta exagerar: el MVP será real.

---

## 9. Resumen de una página (para decidir)

- **Idea:** ganadora para este premio. Encaje con MTP: excelente.
- **Estado hoy:** dos mitades sin conectar; el MVP nuevo no opera e2e; varias red flags que un jurado de QA vería al clonar.
- **Distancia a "ganador":** corta. La lógica existe; falta el **puente HTTP `/v2`**, arreglar 4 bugs concretos y limpiar el repo. **Fase 1 (~2 semanas) cambia la categoría del proyecto.**
- **Mayor activo:** coste 0 € + privacidad on-premise + RAGAS. **Mayor riesgo:** entregar un MVP que no arranca.
- **Margen:** ~4 meses hasta el 30 oct 2026. Suficiente para Fases 1-2 con holgura.
