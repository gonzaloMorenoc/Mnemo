# Auditoría de vendibilidad/producto — estado post-Bloque A+B

**Fecha:** 2026-06-26 · **Rama:** `main` (al día) · **Método:** auditoría adversarial anclada en código real (archivo:línea), abogado del diablo del comprador/inversor. Solo lectura.
**Pregunta:** ¿el Bloque A+B cerró la brecha "vendido vs real"? ¿Es Mnemo ya vendible por millones (Vía B)? ¿Qué falta?

**Referencia base:** los 6 agujeros del análisis original (`feat/analisis-vendibilidad-ia:docs/auditoria/2026-06-26-sintesis-vendibilidad-ia.md`).

---

## Veredicto

**CASI — pero todavía NO vendible por millones por la Vía B.** El Bloque A+B **cerró la brecha de *credibilidad* (la mitad del problema): el producto ya no miente.** Las dos heridas más letales del informe original están suturadas: (1) la pieza de IA estrella `self_eval` **existe de verdad** (ya no es `None` hardcodeado) y modula el veredicto; (2) el certificado se reencuadró honestamente a "acta de evidencia + sign-off" con disclaimer, convirtiendo un pasivo legal en un activo defendible. La IA pasó de cero a **seis features sustanciales que degradan con honestidad**. Eso desactiva al jurado técnico y gana credibilidad para un AI Award.

**Pero la otra mitad — el *empaquetado comercial* que la tesis de los millones (Vía B) exige — sigue sin construirse.** La Vía B = "revender el certificado/gate como producto recurrente que la consultora vende a SUS clientes". Para eso hacen falta cuatro cimientos que **no existen en `main`**: (a) verificación pública del certificado por un tercero (hoy imposible: endpoint autenticado + clave pública nunca publicada); (b) multi-tenancy de dos niveles (consultora→sus clientes); (c) medición/entitlement por release (la unidad de venta); (d) gate que realmente bloquee (hoy es advisory: depende de la config de GitHub del cliente). Sin esos cuatro, el re-rating 1-2×→8-15× es una aspiración de pitch, no una capacidad del producto.

**Y queda una brecha residual de *capacidad*:** el núcleo del veredicto sigue siendo determinista (correcto y deliberado), pero dos promesas del giro de IA quedaron a medias — el patch IA **no se valida ejecutando el test** y **no hay ECE** ni evals de IA que fallen el build. El "foso" cerró el lazo (las etiquetas humanas SÍ cambian veredictos futuros) pero sigue siendo una tabla de etiquetas con dashboard, no un modelo que compone por cliente.

> **Resumen en una frase:** *el Bloque A+B convirtió a Mnemo de "demo que se vende como producto" en "producto honesto y creíble" — pero la palanca de los millones (Vía B) es producto comercial sin construir, no credibilidad técnica. La distancia que queda es de empaquetado y go-to-market, no de motor.*

**Escala de madurez Vía B (subjetiva, anclada en evidencia):**
- Credibilidad técnica / "no mentir": **8/10** (era ~3/10).
- Protagonismo de IA para el Award: **7/10** (era ~2/10).
- Foso defendible: **4/10** (era ~3/10 — cerró el lazo, pero sin profundidad).
- Soporte de producto para Vía B (reventa): **2/10** (era ~1/10 — casi intacto).

---

## Lo SÓLIDO (lo que de verdad se construyó y aguanta una due-diligence)

### 1. `self_eval` firmado existe y modula el veredicto — la herida #3 está suturada
- `src/certify/certificate.py:31-52` `compute_self_eval()` produce un objeto real (`method`, `engine_calibration`, `run_composition`, `confidence`, `ai_eval`, `evaluated_at`) que **se firma dentro del certificado** (`src/certify/service.py:39-48`).
- El `ai_eval` con `faithfulness < 0.5` **degrada `confidence` a `low`** y nunca lo infla (`certificate.py:38-39`), y `confidence == "low"` **baja el veredicto** de `apto` a `apto-con-reservas` (`certificate.py:66-67`). Es una pieza de IA que **modera el juicio firmado**, exactamente la "Apuesta 1" del plan.
- Tested: `tests/test_certificate.py:42-52`, `tests/test_certify_service_selfeval.py`, `tests/test_certify_service_aieval.py`. **Esto es lo más valioso del Bloque A+B: nadie en QA firma una nota auditable sobre la calidad de su propia IA.**

### 2. El certificado reencuadrado a "acta de evidencia + sign-off" — la herida #1 está suturada
- `attestation_type: "evidence_and_assessment"` + `_DISCLAIMER` explícito ("señal asistida, no una garantía de ausencia de defectos ni una certificación de aptitud legal") (`src/certify/certificate.py:5-10, 105-107`), firmado y tested (`tests/test_certificate.py:51-52`, `tests/test_certificate_render.py:15`).
- Convierte el "APTO firmado que deja pasar un bug = prueba documental de culpa" en "firmamos *hechos* + aprobaciones humanas". **Pasivo legal → activo defendible.** Postura de ingeniería impecable.

### 3. Criptografía Ed25519 real + persistencia append-only verificable
- `src/certify/signing.py:18-31` usa `cryptography.hazmat` (Ed25519 genuino, no stub); canonicalización estable `sort_keys + separators` (`signing.py:12-15`); tests de tamper (`tests/test_certify_signing.py:28-36`).
- Persistencia append-only por grant: `grant select, insert` (sin update/delete) en `db/migrations/014_certificates.sql:24`, con RLS+force+`is_org_member`. La firma + canonical JSON se guardan y son re-verificables. **El sustrato de confianza es real.**

### 4. La IA pasó de cero a seis features sustanciales — y todas degradan con honestidad
Esto desactiva la herida #3 ("ángulo IA débil para un AI Award"):
- **Generación estructurada** base con degradación configurable (`src/ai/generate.py:29-54`, `on_failure` 'none'/'fallback').
- **LLM-judge** (faithfulness/groundedness) que alimenta `ai_eval` (`src/ai/judge.py`).
- **Causa-raíz estructurada con citas + linaje cross-proyecto** (`src/assurance/root_cause.py`): muestrea fallos, extrae el top-frame no-interno, pide JSON con `citations` a los ids de evidencia, normaliza inmutablemente (`root_cause.py:94-104`). Endpoint `POST /v2/defects/{id}/root-cause` con caché (`api_v2.py:717-737`).
- **NL sobre el Defect DNA** (`src/ai/nl_query.py`) + búsqueda semántica pgvector, endpoint `POST /v2/defects/ask`.
- **Briefing ejecutivo del run** citado, `GET /v2/runs/{run_id}/briefing` (`api_v2.py:943-967`), degrada a plantilla determinista (`src/ai/briefing.py:48-59`).
- **AIRepairActuator** (parche más allá del locator) cableado como fallback del self-heal determinista (`api_v2.py:267`, `src/actions/service.py:65-70`).
- **Patrón transversal de honestidad:** todas envuelven en `try/except → degradación`, nunca lanzan, y la degradación está tested en 7 ficheros (`tests/test_ai_*.py`, `test_api_v2_briefing.py`, `test_api_v2_defects_ask.py`, `test_certify_service_aieval.py`). El comentario recurrente "el judge nunca rompe la emisión del certificado" (`service.py:37`) refleja una disciplina real. **Quitar el LLM ya no rompe nada — y eso es vendible: "IA donde multiplico, determinismo donde firmo" es literalmente cierto en el código.**

### 5. El lazo del "foso" está CERRADO (mejor que en el informe original)
- Una etiqueta humana sobre una familia **cambia veredictos futuros**: `set_family_label` escribe `defect_families.label` + log append-only `triage_corrections` (`src/defects/repository.py:832-872`); R0 la aplica (`src/triage/engine.py:23-27`, `confidence=0.95`, `requires_approval=False`). Tested end-to-end: `tests/test_triage_repository.py:174-182` + `tests/test_triage_engine.py:66-68`. El informe original lo daba como "etiquetado manual sin feedback"; **ahora el lazo se cierra y está probado.**

### 6. Human-in-the-loop real + atomicidad + higiene cumplida
- Máquina de estados `proposed→approved→materializing` con compare-and-set y recuperación de lock stale 15 min (`src/actions/repository.py:145-161`); nada externo sin approve autenticado (`service.py:37`, `api_v2.py:806-837`); PRs siempre `draft` (`github_app.py:148`). `NullCodeHost` no escribe nada por defecto (`base.py:25-33`).
- **Higiene del informe original cumplida:** modelo LLM fijado al vigente `claude-haiku-4-5-20251001` (ya no el alias obsoleto) (`src/llm/factory.py:10`); legacy RAG archivado a `legacy/` (`legacy/seed_demo.py`, `legacy/DEMO.md`); gate determinista con golden en CI (`backend-ci.yml:40-41`).
- **Cold-start del certificado real:** `n < 30 corrections → "low" → apto-con-reservas` (`certificate.py:12-28`). Atenúa el veredicto cuando el tenant es nuevo — desactiva parte de la herida #2.

---

## Lo FRÁGIL / HUMO (lo que se narra mejor de lo que el código sostiene)

### F1. El "foso" cerró el lazo pero NO es un modelo que componga — es una tabla de etiquetas con dashboard
- `tenant_accuracy` / `n_corrections` se **miden y muestran, pero NUNCA realimentan una decisión de triaje**: `get_calibration_metrics` (`repository.py:874-897`) solo lo consumen el dashboard (`api_v2.py:709`) y la *confianza del certificado* (`certify/service.py:28`, `certify/gate.py:43`). **Nunca lo importa `triage/engine.py`.** La confianza de R0 es un `0.95` hardcodeado con independencia de si la precisión real del tenant es 95% o 50% (`engine.py:25`).
- **Cero ML/distilación/fine-tuning por tenant:** grep `distill|fine-tun|train|sklearn|torch|.pkl` → cero. El "foso futuro pavimentado por el lazo" es aspiracional. El moat es **gravedad de datos tipo CRM** (un competidor re-elicita las etiquetas en semanas de uso), no un network effect ni pesos entrenados.
- **Veredicto adversarial:** defendible como "aprendemos las preferencias de triaje de tu equipo y dejamos de re-preguntar" (cierto y tested). **NO** defendible como "un modelo que aumenta su precisión por cliente con el tiempo" — eso es humo.

### F2. La novedad sigue siendo deduplicación disfrazada (herida #2 solo medio suturada)
- `"is_novel": (fam not in recurrent)` (`repository.py:733`): "novel" = fingerprint/familia no visto en un run anterior. No es comprensión de bugs; es dedup. El rename a "fallo de aserción sin precedente" **NO se aplicó** (grep cero); solo se suavizó cosméticamente en el renderer (`certify/render.py:12` "real (sin precedente en el histórico)"). La regla sigue siendo `R5_real_novel` en código.
- Cold-start atenúa el *certificado* (F sólido #6) pero **no la verdad de R5**: un tenant nuevo con `is_novel=True` en casi todo sigue generando `R5_real_novel` → `requires_approval=True` (`engine.py:37-38, 46`). En el piloto, "todo es novel → todo pide aprobación" (la objeción original) **persiste a nivel de triaje**, aunque el certificado ya no grita "no-apto" rotundo.

### F3. La aplicación del self-heal sigue siendo `content.replace(old, new, 1)` (herida #4 medio suturada)
- El **proposal** mejoró mucho (motor DOM-diff real con scoring y gates anti-ambigüedad: `src/actions/selfheal/`), **pero la aplicación al repo es literal**: `new_content = content.replace(old_str, new_str, 1)` (`src/ci/github_app.py:68`). Exige que el locator aparezca **byte-a-byte** en el fichero; si el test escribió comillas/espacios distintos, es no-op y degrada (honesto pero frágil). **Solo Playwright + TypeScript** (todos los regex/emisores son sintaxis Playwright JS/TS).
- Comoditizado: Testim/mabl/Healenium/Playwright ya hacen reparación de locator, y algunos a nivel runtime/AST (más robusto que un `str.replace` que exige match literal). El diferenciador real no es el self-heal sino **la decisión de triaje de SI curar** (R3 maintenance vs ticket) — eso sí es más defendible, pero es una idea, no un moat.

### F4. La salvaguarda anti-enmascaramiento es PROSA, no un gate (herida #6 incumplida)
- `masking_risk` se **escribe** como flag en el payload (`selfheal.py:59`, `ai_repair.py:55`) pero **nunca se lee como condición** en ninguna parte — solo se asierta en tests. El "aviso" anti-enmascaramiento es **texto inyectado en el cuerpo del PR** (`src/actions/service.py:19-21, 29-31`), no lógica.
- **No existe análisis del diff del commit** en todo `src/` (grep `git diff`/changed-files → cero). El "no auto-clasificar mantenimiento si el commit tocó código de producción de la ruta bajo prueba" del informe original **no está implementado**. El proxy R3 (solo cura `maintenance` con baseline verde + DOM cambiado, no `assertion_failure`) es razonable pero no inspecciona el diff. El masking risk para fallos *recurrentes* mal etiquetados sigue abierto (`tests/test_triage_engine.py:85-87`: una familia mal etiquetada "flaky" que un día caza un assertion recurrente sigue saliendo flaky a 0.95).

### F5. El patch IA NO se valida ejecutando el test (herida del "wow", Apuesta 4 incumplida)
- `AIRepairActuator.propose` solo valida: (a) `old_block` es substring literal del source, (b) old≠new, (c) confianza auto-reportada del LLM ≥ 0.5 (`src/actions/ai_repair.py:48-50`). **No hay sandbox, runner ni ejecución** (grep `subprocess|docker|npx|create_subprocess` en `src/` → cero). Se materializa como draft PR vía el mismo `str.replace`, etiquetado "NO auto-validado" (honesto). La promesa "parche validado ejecutando el test" del plan **no se cumplió** — es una sugerencia basada en la auto-confianza del LLM.

### F6. La medición de "IA de verdad" es fina: NO hay ECE y los evals de IA NO fallan el build
- **ECE ausente por completo** (grep con word-boundary → cero). El informe original lo pedía explícitamente "para convertir el cap de confianza 0.70 de corazonada en número calibrado". Sigue siendo corazonada (`tiebreaker` escribe `0.70` fijo, `triage/service.py:84-87`; R0 escribe `0.95` fijo).
- **El eval en CI solo cubre el motor DETERMINISTA**: `backend-ci.yml:41` corre `eval_ai.py --min-accuracy 0.8`, que es triaje sin LLM (`scripts/eval_ai.py:1-2`, "Sin LLM (corre en CI)"). **El LLM-judge / faithfulness NO falla el build.** La promesa "Mnemo se aplica su propia medicina de Assurance / evals de IA que fallan si la precisión regresa" **solo se cumple para el determinismo, no para la IA.**
- **Golden set diminuto: 10 casos** (`tests/golden/golden_triage.jsonl`), todos del motor determinista. No hay golden de self-heal ni de causa-raíz. Como prueba de rigor ante un inversor técnico, es delgado.

### F7. NO hay demo e2e del lazo que se vende (herida #5 sin cerrar)
- `scripts/smoke_demo.sh` solo prueba health + login + un endpoint autenticado (`/v2/orgs`). **No ejecuta los 3 actos** (ingest → triaje → acción → certificado/gate). El seed sigue siendo el flujo legacy (`legacy/seed_demo.py`). Hay tests unitarios con mocks, pero **no se puede enseñar el lazo completo funcionando end-to-end**. Para una demo de concurso, esto es el agujero más visible que queda.

### F8. El PDF pulido no existe; el deliverable es HTML crudo
- `src/certify/render.py:15-58` devuelve HTML inline (`<table border='1'>`), servido como `HTMLResponse`. Grep `reportlab|weasyprint|pdfkit|application/pdf` → solo ingestión *entrante* de PDF, nada que *produzca* el certificado en PDF. El "entregable pulido (PDF)" del plan (Bloque C) no está hecho — esperado (Bloque C no se ha abordado), pero relevante para "el certificado como artefacto vendible".

---

## Brecha residual: lo que sigue siendo "vendido pero no real"

Ordenado por letalidad para la tesis de los millones (Vía B):

1. **El tercero NO puede verificar el certificado — y esa es la esencia de la Vía B.** `POST /v2/certificates/verify` exige JWT de la misma org (`api_v2.py:890-900`, `Depends(get_current_user)`); **la clave pública de firma nunca se publica** (no hay `/jwks` ni `.well-known` para la clave de Mnemo). Un cliente de la consultora (el tercero que debería *confiar* en el certificado) hoy no tiene endpoint anónimo ni clave para verificar offline. **Se vende "un artefacto que tu cliente puede verificar"; el código no lo permite.** Además, la canonicalización no es RFC 8785 (JCS), así que una re-serialización en otro lenguaje podría no reproducir los bytes firmados → no portable. Y no hay `key_id`/rotación: si la clave rota, todo certificado previo queda inverificable.

2. **No hay multi-tenancy de dos niveles (consultora → sus clientes).** La tenancy es de un nivel: `org` + `memberships`, todo gateado por `is_org_member` (`014_certificates.sql:22-23`). No existe org padre/reseller con orgs hijas aisladas. La consultora tendría que ser *miembro* de cada org cliente, sin el modelo "revendo Mnemo a 10 clientes bajo mi marca, cada uno ve solo lo suyo". **El modelo de negocio Vía B no tiene sustrato técnico de aislamiento.**

3. **No hay medición/entitlement por release — la unidad de venta no se puede facturar.** Grep `billing|metering|entitlement|quota|usage|stripe|subscription` → cero. Nada cuenta certificados, los limita por plan, ni emite un evento de uso. "Certificado por release como unidad de venta" no tiene contador ni enforcement: inferirías facturación de un `count(*)` a posteriori, sin control. **Sin esto no hay ARR pegajoso medible.**

4. **El gate es advisory, no bloqueante.** `publish_check_run` hace una llamada real a la Checks API de GitHub (`github_app.py:155-167`, SÓLIDO), pero un check `failure` solo bloquea si el cliente configuró `mnemo/assurance` como *required status check* en branch protection — y Mnemo ni lo configura ni lo verifica (no hay código de branch-protection). Peor: `apto-con-reservas → neutral`, y GitHub trata `neutral` como **no bloqueante aunque sea required** (`certify/gate.py:5`). **"El gate bloquea el deploy" es condicional a la config del cliente; el producto entrega una señal advisory.**

5. **La autoridad del certificado es auto-declarada y auto-limitada (por diseño).** El disclaimer renuncia explícitamente a la autoridad legal que la Vía B querría vender (`certificate.py:5-10`). Es la postura de ingeniería *correcta* pero la comercial *incómoda*: una firma sobre la salida de un motor de reglas prueba "Mnemo afirmó X sobre el run Y sin manipulación", no transfiere responsabilidad ni confiere autoridad externa. **El crypto es real; la *autoridad* no — y para "millones por certificación con autoridad" la autoridad es el producto.**

6. **Cero prueba económica con clientes reales.** (Transversal del informe original, intacto.) Nunca tocó un CI de pago; no hay un solo número de ROI medido en producción. Un inversor que paga 8-15× exige la prueba de que el certificado mueve el P&L del comprador, no una demo.

---

## Qué falta para "vendible por millones" (Vía B), priorizado

Ordenado por **desbloqueo de la tesis × factibilidad** (lo barato y letal primero). Nada de esto es "reescribir el motor": es empaquetado comercial + cerrar dos promesas de IA.

### P0 — Sin esto, la Vía B es imposible (no opcional)
1. **Verificación pública e independiente del certificado.** (a) Endpoint anónimo `GET /.well-known/mnemo-cert-key` que publica la clave pública con `key_id` + historial de rotación; (b) endpoint de verificación *sin auth* o un verificador offline standalone; (c) añadir `key_id` al certificado firmado y adoptar canonicalización portable (RFC 8785 / JCS). **Es el corazón de "tu cliente puede confiar en el certificado". Barato (la cripto ya existe).** Sin esto, Vía B no arranca.
2. **Multi-tenancy de dos niveles (reseller → clientes).** Modelo de org padre/hija con aislamiento, para que la consultora revenda bajo su marca. Toca el modelo de datos y RLS — el trabajo más grande de la lista, pero es **el sustrato del negocio recurrente**.
3. **Medición + entitlement por release.** Contador de certificados/gates por org+plan, evento de uso, enforcement de cuota. Convierte "certificado por release" en una unidad facturable y en ARR medible. Barato-medio.

### P1 — Cierra las promesas de IA/credibilidad a medias (defiende el Award y la due-diligence)
4. **Validar el patch IA ejecutando el test** (Apuesta 4 real): sandbox containerizado `npx playwright test <fichero>` sobre la rama candidata antes de sacar el PR de draft. Mata la objeción "es un `str.replace`/auto-confianza del LLM" (F5).
5. **ECE + evals de IA que fallen el build** (rigor de "IA de verdad"): calcular ECE sobre las decisiones LLM-asistidas, reemplazar los `0.95`/`0.70` fijos por confianza calibrada, y añadir un job en CI que falle si faithfulness/precisión-IA regresan. Golden sets de self-heal y causa-raíz (hoy 10 casos solo de triaje). (F1, F6).
6. **Salvaguarda anti-enmascaramiento real** (gate, no prosa): leer el diff del commit (GitHub compare API), y *leer* `masking_risk` para bloquear/degradar la materialización del self-heal cuando el código de producción de la ruta bajo prueba cambió. (F4).

### P2 — Hace que el gate y el certificado *vendan* (lo que se ve y se factura)
7. **Gate realmente bloqueante**: gestionar (o guiar la config de) branch protection para hacer `mnemo/assurance` required, y decidir conscientemente la semántica de `neutral`. (Brecha residual #4).
8. **Demo e2e del lazo de 3 actos** sembrada y reproducible (no solo smoke de auth), con plan B grabado. (F7, herida #5).
9. **Certificado como entregable pulido (PDF)** con marca/letterhead, y publicar la verificación en el propio PDF. (F8).

### P3 — Profundiza el foso y prueba la economía (post-credibilidad)
10. **Calibración que realimente la decisión** (no solo el dashboard): que `tenant_accuracy` module la confianza de R0 y el umbral de aprobación; decay/re-verificación de priors para que las etiquetas no fosilicen. Convierte el "foso" de tabla-de-etiquetas en algo que compone. (F1, F2).
11. **Una prueba económica real** con un CI de pago y un número de ROI medido. Es lo que un inversor a 8-15× exige por encima de cualquier feature.

---

## Conclusión

El Bloque A+B fue un acierto estratégico y bien ejecutado en lo técnico: **eligió suturar la credibilidad antes que añadir motor, y lo logró** — el producto ya no se vende como algo que no es, la IA es protagonista real y honesta, y el certificado es un activo defendible en vez de un pasivo. Eso vale para *ganar el Award* (la narrativa "determinismo donde firmo, IA donde multiplico" ahora es literalmente cierta en el código) y para *sobrevivir una due-diligence técnica*.

**Lo que NO resolvió — y es donde están los millones — es el producto comercial de la Vía B:** verificación por terceros, multi-tenancy de reseller, medición por release y un gate bloqueante. Esas cuatro piezas son **empaquetado, no motor**, y siguen sin construirse. Hasta que existan, "vendible por millones vía reventa del certificado" es una tesis de pitch, no una capacidad del producto.

**Casi. La distancia que queda es corta en esfuerzo (es empaquetado + cerrar dos promesas de IA) pero es 100% bloqueante para la tesis de los millones.**
