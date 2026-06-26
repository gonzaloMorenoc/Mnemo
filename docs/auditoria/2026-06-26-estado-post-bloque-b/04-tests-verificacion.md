# Auditoría de Tests y Calidad de Verificación — Mnemo Autopilot

**Fecha:** 2026-06-26 · **Rama:** `main` (al día) · **Alcance:** calidad de la red de seguridad de un producto que *firma si un release es apto*.
**Método:** solo lectura de código/git + colección de tests (no se ejecutó la suite). Evidencia con `archivo:línea`.

**Inventario verificado:**
- `src/`: 96 archivos `.py`, **7 253 líneas**.
- Tests: 113 archivos, **585 funciones `def test_`**, **589 colectadas** → **504 unit** (`-m "not integration"`) + **85 integración** (`@pytest.mark.integration`, 15 archivos).
- Eval: `tests/golden/golden_triage.jsonl` (**10 casos**) + `scripts/eval_ai.py` + paso en CI (`backend-ci.yml:40-41`).
- `ragas==0.4.3` y `pytest==9.0.2` en `requirements.txt`. **`pytest-cov` NO está instalado.**

---

## 1. Veredicto

**La red de seguridad es buena para un proyecto normal, pero NO es todavía "ejemplar" para un producto que vende el acto de certificar releases.** El núcleo determinista (triaje, firma Ed25519, gate, máquina de estados de acciones) está testeado de forma genuinamente conductual y hasta adversarial. Pero la verificación tiene **tres agujeros estructurales que un producto-que-certifica no se puede permitir**, y todos comparten una misma causa raíz: *las partes más críticas se prueban contra el mundo real solo en local, y nunca en CI*.

1. **El "eval de IA" de CI no evalúa IA.** `scripts/eval_ai.py` (lo que CI etiqueta como *"AI eval (golden de triaje)"*, `backend-ci.yml:40`) ejecuta el **motor DETERMINISTA** de triaje (`from src.triage.engine import triage`, `eval_ai.py:11`). No hay ni un LLM en ese paso. El único eval real de calidad de modelo (RAGAS + judge contra Ollama) está en tests `@pytest.mark.integration` que **se saltan en CI** y solo corren en local con Ollama levantado.
2. **El "80% mínimo" es aspiracional, no medido.** No hay `pytest-cov`, ni `--cov`, ni `fail_under` en ningún sitio (`backend-ci.yml`, `pytest.ini`, `requirements.txt` sin cobertura). Nadie mide la cobertura; el número 80% no se aplica en ningún gate.
3. **RLS — la garantía de aislamiento multitenant — se afirma por metadatos, no por comportamiento.** `test_migration_016_rls.py` solo lee `pg_class.relrowsecurity`/`relforcerowsecurity`; **ningún test se conecta como org-A y demuestra que físicamente no puede leer filas de org-B**. El aislamiento se prueba en la capa Python (que filtra por membership), no en las *policies* de Postgres.

**Nota global: 7 / 10.** Sólido en lo determinista; con deuda real en eval-de-IA, medición de cobertura y verificación de RLS a nivel de BD. Para el pitch MTP es defendible; para la promesa "yo firmo si es apto" hay que cerrar los gaps P0/P1 de abajo.

---

## 2. Cobertura por módulo

### 2.1 Núcleo determinista — **bien cubierto**
| Área | Módulos | Veredicto |
|---|---|---|
| `triage/` | signals, service, patterns, tiebreaker, **engine** (15 fns, R0–R6 + conflictos + safety-net), evidence, dom | **WELL-TESTED** — ramas flaky/infra/maintenance/real/unknown con edge cases y orden de prioridad. |
| `certify/` | **signing** (firma Ed25519 real, tamper-detection), certificate (confidence/verdict/risk), gate, service | **WELL-TESTED** — la firma se verifica de verdad con keypair real y round-trip JSONB (`test_certificate.py:88-129`). |
| `actions/` | service (19 fns), ticket, ai_repair, quarantine, base | **WELL-TESTED**. |
| `actions/selfheal/` | selector, locator, selfheal (14 fns), candidates, dom | **WELL-TESTED**, salvo `explainer.py` (ver §3). |
| `ingest/` (8 parsers) | junit, playwright, cypress, testng, allure, cucumber, robot, detect | **WELL-TESTED** con fixtures reales y aserción de campos extraídos; `robot.py` THIN (solo happy + XML inválido). |
| `ci/` | github_app (14 fns en 4 archivos), github_auth, mapping, models, **webhook_auth** | **WELL-TESTED**; `webhook_auth` con casos de ataque (firma mala/secreto erróneo/sin prefijo/fail-closed). |
| `defects/` | fingerprint, centroid, match, ingestion_service | **WELL-TESTED** a nivel aritmético. |
| `jira/` | models, mapper, client, export, **safe_url** (SSRF blocked), ingestion_service | **WELL-TESTED** (con matices de seguridad en §4). |
| `assurance/` | root_cause (14 fns en 4 archivos), narrator, verdict | **WELL-TESTED**, incl. hardening anti-prompt-injection (`test_root_cause_prompt.py:29-34`). |
| `api_v2.py` (974 líneas) | 13 archivos `test_api_v2_*` (~101 fns) | **WELL-TESTED** como contrato (shapes, auth-gating, degradación) — pero todo **mockeado, sin BD** (ver §5). |
| `llm/` | factory (11 fns), reasoning (strip), provider | **WELL-TESTED**; los *providers* concretos THIN (SDK stubbeado, ver §3). |

### 2.2 Sin test directo o solo "import-smoke" — **el pasivo**
| Módulo | Líneas | Estado | Riesgo |
|---|---|---|---|
| `src/tenant_kb.py` | **505** | solo `test_imports.py` + stub dataclass | **ALTO** — repositorio multitenant de ingesta/RLS/embeddings; `ingest_file`, `_search_scope`, `_insert_chunks_and_embeddings`, claim-setting RLS sin un solo test de comportamiento. |
| `src/loader.py` | 131 | **0 tests** | MEDIO — parsing de ficheros (boundary de input no confiable). |
| `src/structured_analyzer.py` | 95 | solo `test_imports.py` | MEDIO. |
| `src/history.py` | 81 | **0 tests** | BAJO/MEDIO. |
| `src/vector_store.py` | 60 | **0 tests** | MEDIO (RAG v1). |
| `src/retriever.py` | 58 | **0 tests** | MEDIO (RAG v1). |
| `src/inspector.py` | 36 | **0 tests** | BAJO. |
| `src/model.py` | 25 | **0 tests** | BAJO (glue LangChain v1). |
| `src/prompts.py` | 20 | **0 tests** | BAJO. |

Confirmado por `grep`: ninguno de los 7 módulos "0 tests" es importado por archivo de test alguno. La mayoría es el **pipeline RAG v1 single-tenant legacy** (probablemente fuera del camino crítico de Autopilot, pero sigue desplegado y sin red).

### 2.3 Cobertura "fantasma": ~280–1 000 líneas que en CI se prueban con CERO aserciones
`defects/repository.py` (**988 líneas**, el módulo más grande del repo — data-access, dedup, búsqueda vectorial, RLS), `actions/repository.py` (191), `certify/repository.py` (91), `triage/repository.py`, `ci/repository.py` y `integrations_repository.py` **solo** se prueban con tests `@pytest.mark.integration` que hacen `pytest.skip()` sin `DATABASE_URL`. En un runner sin BD (que es exactamente CI, §5), **ese código corre 0 aserciones y la suite sigue verde**. La capa de persistencia — donde vive la garantía de aislamiento real — no tiene red en CI.

### 2.4 ¿El 80% es real o aspiracional?
**Aspiracional.** No hay instrumentación de cobertura en ningún punto. Dado que ~1 200+ líneas de repositorios + 600 de `tenant_kb`/`structured_analyzer` + ~470 del RAG v1 **no se ejercitan en CI**, la cobertura *de línea real en CI* está con casi total seguridad **por debajo del 80%**, aunque la suite local con BD se acerque más.

---

## 3. Calidad de los tests

**Lo bueno (de verdad):** no encontré `assert True`, ni no-ops, ni tests que mockeen la unidad bajo prueba en el núcleo. Varios tests son **ejemplares y adversariales**, justo donde más importa para este producto:

- **El veredicto del LLM NUNCA puede sobreescribir al certificado determinista** — `test_api_v2_briefing.py:56-78`: el LLM falso devuelve `verdict_line:"NO-APTO-LLM"` y se asevera que la respuesta es `"apto"` (del cert) y `!= "NO-APTO-LLM"`. Exactamente la prueba correcta para un certificador.
- **La IA solo puede DEGRADAR, nunca inflar la confianza** — `test_certificate.py:66-72` (faithfulness 0.3 → confidence "low" aunque la calibración sea alta) y `test_certificate.py:80-85` (faithfulness 0.99 NO infla; manda el cold-start). La regla `_LOW_FAITHFULNESS=0.5` de `certificate.py:38` está testeada en ambas direcciones, más tamper-detection de la firma (`test_certificate.py:99,128`).
- **Degradación elegante real** (no overrides inertes): `test_api_v2_briefing.py:117-132` parchea `get_llm_provider` con `side_effect=RuntimeError` y exige 200 con resumen degradado; el propio docstring (`:36-39`) documenta que `dependency_overrides` sería inerte aquí y usa `mock.patch` — autor de tests sofisticado.
- **Root-cause degradado NO cachea y devuelve 503** (`test_api_v2_root_cause.py:97-104`) — gate de calidad genuino.

**Lo débil (muestreo del Bloque B y núcleo):**

1. **`tests/test_ai_judge.py:20-23` — el LLM-as-judge nunca se prueba como juez.** `judge.py` es el oráculo de auto-evaluación: un LLM puntúa `faithfulness`/`groundedness` de los veredictos `llm_assisted` del propio Mnemo. Todos los tests le inyectan un JSON literal (`'{"faithfulness":0.8,"groundedness":0.7}'`) y aseveran que se devuelve igual. **No existe en ningún sitio un test del tipo "afirmación fabricada + evidencia que la contradice → faithfulness < 0.5".** Lo único conductual que se ejercita es `_clamp` (`judge.py:17-21`). Consecuencia crítica: la regla de seguridad de §3 (faithfulness bajo degrada el veredicto) está bien testeada *en su plumbing*, pero **la señal que la dispara proviene de un oráculo cuya corrección jamás se verifica**. Un judge que devolviera 0.9 a todo (incluido contenido inventado) pasaría toda la suite y emitiría certificados "apto" con confianza alta.

2. **`tests/test_evaluation.py:117-131` y `:147-161` — aserciones tautológicas sobre RAGAS.** `test_metrics_in_valid_range` mockea RAGAS para devolver `0.85/0.90/...` y luego asevera `0.0 <= v <= 1.0`: comprueba que constantes escritas a mano están en [0,1]. `test_with_reference` mockea `evaluate→{faithfulness:0.9}` y asevera `result["faithfulness"]==0.9`: el mock devuelve lo que se le dijo. No miden nada del modelo.

3. **`tests/test_imports.py:4-9` — 600 líneas sobre un smoke test.** Es la única "cobertura" de `tenant_kb.py` (505) y `structured_analyzer.py` (95): solo asevera que `import` no lanza. Lógica de ingesta/RLS/embeddings sin verificación de comportamiento.

4. **`tests/test_llm_providers.py:6-9, 12-30` — los clientes SDK reales nunca se construyen.** Se stubbea `p._llm`/`p._client` con lambdas/clases falsas; las líneas reales `from anthropic import Anthropic` / `from openai import OpenAI` / `OllamaLLM(...)` (`providers/*.py:11-16`) no se ejecutan. Sí se prueba el *parsing* de la respuesta (extraer `.choices[0].message.content`, unir bloques Anthropic) — eso vale — pero "¿llamamos bien al SDK real?" no.

5. **`tests/test_certify_render.py:25-27` + `test_certificate_render.py` — render por "substring-in-blob".** Dos archivos finos sobre el mismo módulo de 58 líneas (`render.py`) con checks `"apto" in html`. **No hay test de escape de HTML** sobre valores controlados por el tenant (p. ej. `project`/`failure_id` con `<script>`) → único gap de seguridad genuino en la capa de render.

**Mención (gap por omisión):** `actions/selfheal/explainer.py` (`LLMSelfHealExplainer`, construcción de prompt + `strip_reasoning`) **no se importa en ningún test**; solo se ejercita vía un `MagicMock` pasado al actuator (`test_selfheal_actuator.py:36-43`). Un bug en `_build_prompt` o en el wrapping de `strip_reasoning` sería invisible. Inconsistente: el análogo `tiebreaker._build_prompt` sí tiene test directo.

---

## 4. Integración

**Cobertura (85 tests, 15 archivos; corren contra Postgres de PROD con seed+cleanup):**

- **BIEN cubierto a nivel repositorio (BD real):**
  - **Ingesta idempotente** — fuerte: `test_ci_ingestion_idempotency.py` + `test_ci_repository.py::test_ingest_ci_run_idempotent_by_run_uid` / `..._dedup_does_not_duplicate_or_bump_dna` + rollback atómico.
  - **Triaje persistido** — `test_triage_repository.py` (upsert idempotente: 1 fila no 2, round-trip de `evidence_bundle`).
  - **Firma + persistencia del certificado** — `test_certify_repository.py::test_signature_survives_jsonb_roundtrip` (build → sign Ed25519 → save → reload → verify contra BD real); save rechazado a no-miembro.
  - **Aislamiento multitenant en la capa Python** — extenso (`*_non_member`, `*_wrong_org_isolation`, `*_foreign_run` → `None`/`[]`/`PermissionError`).

- **NO cubierto / débil:**
  - **RLS a nivel de policy de BD — NO probado.** `test_migration_016_rls.py` solo introspecciona flags `pg_class`. **Ningún test se conecta como rol de org-A y prueba que no puede `SELECT` filas de org-B.** Si un path de query olvidara el filtro de membership, estos tests no detectarían la fuga. (P0 — es *la* garantía que vende el producto.)
  - **Endpoints API contra BD real — NO existe.** Los 13 `test_api_v2_*` usan `TestClient` con `dependency_overrides=lambda: MagicMock()` y LLM parcheado; **ninguno** está marcado `integration`. El camino HTTP→repositorio→Postgres nunca se ejercita end-to-end.
  - **Gate de certificado end-to-end — NO existe.** `test_api_v2_gate.py` mockea el gate. No hay un test ingest → triage → certificate → gate-publish contra BD real.
  - El `TestRAGASIntegration` de `test_evaluation.py` requiere Ollama y se auto-salta si no está.

**Fiabilidad del cleanup (corre sobre PROD — punto sensible):**

- **No hay fixture central de seed/cleanup.** `tests/conftest.py` (22 líneas) solo carga JSON; cada archivo de integración define su propia fixture `org`/`repo` casi idéntica (ej. `test_assurance_repository.py:49-73`).
- **Teardown tras fallo de test: SÍ (mayormente).** El cleanup vive en la sección post-`yield`; pytest ejecuta teardown aunque el cuerpo del test falle. Dos fixtures que siembran una 2ª org inline usan `try/finally` explícito (`test_triage_repository.py:313/321, 400/408`).
- **Scoping: SEGURO.** Todo `delete` es `where id = %s` ligado al `uuid4()` creado por esa fixture. **Ni un `TRUNCATE`, ni `DELETE` sin filtro, ni delete-por-patrón.** **No puede borrar datos reales de tenants.** Las filas hijas se limpian por `ON DELETE CASCADE` (14 FKs confirmados a `public.organizations`). *Caveat:* 2 FKs son `ON DELETE SET NULL` (`profiles.default_org_id`, `analyses.org_id`, `db/migrations/001_multitenant_kb.sql:33,99`) — pero esta suite no escribe esas tablas.
- **Riesgo residual: filas huérfanas en PROD.** El cleanup vive en teardown de fixture, **no en un barrido garantizado**. Si el proceso se mata a mitad (SIGKILL / timeout de CI) o el seed falla en la ventana estrecha post-`commit`/pre-`yield`, quedan filas huérfanas en las tablas `public` de PRODUCCIÓN. No hay tenant de test aislado, ni flag `is_test`, ni separación de esquema: los datos transitorios de test se escriben en las mismas tablas que producción.

**¿Corre en CI? NO — solo local.** `backend-ci.yml:39`: `python -m pytest -m "not integration" -q` (job llamado *"Pytest (unit)"*). Los 85 tests de integración (BD + Ollama) corren **solo cuando un dev los lanza en local con `DATABASE_URL`** — y ese `DATABASE_URL` está documentado como **PROD** (memoria del proyecto). Cada test se auto-salta sin `DATABASE_URL`.

---

## 5. Eval de IA

**Veredicto: hoy es mayormente DECORATIVO en lo que CI hace cumplir; el eval serio existe pero está apagado por defecto.**

- **El paso "AI eval" de CI no toca IA.** `scripts/eval_ai.py` evalúa el **motor determinista** (`eval_ai.py:11,17-28`): aplica `triage(Signals(**c["signals"]))` y compara categoría contra el golden. El umbral `--min-accuracy 0.8` (`backend-ci.yml:41`) **sí falla el build** si baja — eso es bueno —, pero es un eval del **árbol de decisión determinista**, no de un LLM. La etiqueta "AI eval" en CI es engañosa.
- **Golden set: 10 casos.** `tests/golden/golden_triage.jsonl` cubre flaky×3, infra×2, maintenance×2, real×2, unknown×1. Suficiente como *smoke* de regresión del árbol de reglas, **insuficiente como golden serio**: sin casos de conflicto/ambigüedad multi-señal, sin variantes por proyecto, sin negativos adversariales. 10 casos / 5 categorías ≈ 2 por clase.
- **El eval de calidad de modelo real existe pero NO está en CI.** `evaluator.py` envuelve RAGAS (`faithfulness`, `response_relevancy`, `llm_context_precision_without_reference`, `llm_context_recall`). Los tests con umbrales reales — `test_evaluation.py:249` (`faithfulness >= 0.5` para respuesta fundamentada), `:264` (`relevancy < 0.7` para irrelevante) — son `@pytest.mark.integration` y hacen `skip` si `curl` a Ollama falla. **No protegen CI** y tienen pinta de poco ejercitados. (Verifiqué que las claves `result["faithfulness"]`/`result["relevancy"]` SÍ existen en la salida de `evaluator.py:61-62` — no hay `KeyError`; el riesgo es que estén apagados, no rotos.)
- **El LLM-judge (`judge.py`) nunca se valida como juez** (§3.1). Es la pieza que justifica el "auto-certifica", y su corrección no tiene ni un test. La buena noticia: su salida solo puede *degradar* el certificado (`certificate.py:38`, nunca inflar), y *eso* sí está testeado — así que un judge roto produce falsos "apto-con-reservas"/"low confidence" (conservador), no falsos "apto" optimistas. El riesgo es de **fiabilidad/ruido**, no de certificar basura como apta… *salvo* que el judge devuelva sistemáticamente alto, en cuyo caso simplemente no aporta señal y nadie lo detectaría.

---

## 6. Gaps priorizados

### P0 — Bloqueantes para "el que firma releases"
1. **RLS no se prueba como comportamiento.** Añadir un test de integración que se conecte con el rol/claims de org-A y demuestre que `SELECT` sobre datos de org-B devuelve 0 filas (a nivel policy de Postgres, no de filtro Python). Hoy una regresión que olvide el filtro de membership en *cualquier* query fugaría datos cross-tenant sin que nada lo atrape. Evidencia: `test_migration_016_rls.py` (solo flags); aislamiento solo en capa Python (`test_*_repository.py`).
2. **El "AI eval" de CI es un nombre equivocado para un eval determinista; el eval de IA real no corre en CI.** O bien (a) levantar Ollama/un judge en CI con umbral que falle el build, o (b) renombrar honestamente el paso a "golden determinista" y mover el eval de calidad de modelo a un gate nocturno/PR que sí se ejecute. Hoy nada hace cumplir faithfulness/groundedness automáticamente. Evidencia: `eval_ai.py:11`, `backend-ci.yml:40-41`, `test_evaluation.py:200-266` (skipped).
3. **El LLM-judge no tiene ni un test de corrección.** Añadir casos golden de judging: afirmación fundamentada → faithfulness alto; afirmación inventada vs evidencia contradictoria → faithfulness < 0.5. Sin esto, el oráculo de auto-evaluación es un punto ciego. Evidencia: `test_ai_judge.py:20-23`.

### P1 — Alto
4. **La cobertura no se mide.** Añadir `pytest-cov` + `--cov=src --cov-fail-under=80` en `backend-ci.yml`. Hoy el "80% mínimo" es folklore; con repositorios + `tenant_kb` + RAG v1 sin ejercitar en CI, la cobertura real de CI casi seguro < 80%. Evidencia: ausencia total de cobertura en `requirements.txt`/`backend-ci.yml`/`pytest.ini`.
5. **`defects/repository.py` (988 líneas) y demás repositorios: 0 aserciones en CI.** Toda su prueba es integración-gated. Opciones: contenedor Postgres+pgvector en CI (servicio de GitHub Actions) para correr la suite de integración, o tests unit con BD en memoria/fakes para las rutas no-SQL. Evidencia: §2.3.
6. **`tenant_kb.py` (505 líneas) solo tiene import-smoke.** Es ingesta/RLS/embeddings multitenant; necesita tests de comportamiento de `ingest_file`/`_search_scope`/claim-setting. Evidencia: `test_imports.py:4-9`.

### P2 — Medio
7. **Endpoints API + gate sin ningún test end-to-end contra BD.** Al menos un *happy-path* de integración ingest→triage→certificate→gate. Evidencia: §4.
8. **Fiabilidad del cleanup en PROD.** Añadir un barrido de sesión `finally`/`pytest_sessionfinish` que borre por convención de namespace (orgs `test-org-*`/`@test.internal`) como red ante procesos matados; mejor aún, un tenant/esquema de test dedicado o correr integración contra una BD efímera, no PROD. Evidencia: cleanup solo en teardown de fixture (`test_assurance_repository.py:49-73`), `DATABASE_URL`=PROD.
9. **Escape de HTML en `render.py` sin test** sobre valores controlados por tenant (`<script>` en `project`/`failure_id`). Evidencia: `test_certify_render.py:25-27`.
10. **Providers LLM concretos + `explainer.py` + RAG v1** (`loader`, `vector_store`, `retriever`, `history`) sin cobertura conductual real. Evidencia: §2.2, §3.4, §3-mención.

### Lo que NO me preocupa (positivos a preservar)
- Firma Ed25519: verificada de verdad (keypair real, tamper, round-trip JSONB).
- Árbol de triaje: ramas + prioridad + safety-net cubiertos.
- Invariantes adversariales clave: "el cert manda sobre el LLM" y "la IA solo degrada, nunca infla" están testeados.
- Webhook HMAC y SSRF (safe_url): casos de ataque presentes (con matiz de resolver stubbeado / sin DNS-rebinding).
- Degradación elegante (LLM caído → 200/502/503 según contrato): bien probada y con autoría cuidadosa.

---

*Fin del informe.*
