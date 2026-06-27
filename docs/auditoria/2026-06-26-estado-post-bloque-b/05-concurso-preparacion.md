# Auditoría de preparación para el concurso — Mnemo Autopilot (2026-06-26)

**Premio:** MTP AI Innovation Award · **Deadline:** 30-oct-2026 · **Hoy:** 2026-06-26 (~4 meses / ~18 semanas).
**Alcance:** preparación para *ganar* (demo + pitch + riesgos de entrega + elegibilidad). Solo lectura del código en `main` (`6929d77`, Bloque B mergeado: B1–B5).
**Método:** inventario del repo + 4 sondas en paralelo (certificado/`self_eval`/PDF, telemetría/métricas, frontend, pipeline e2e), contrastadas con la auditoría profunda previa (`docs/auditoria/2026-06-25-auditoria-profunda.md`, items D1–D4) y el plan estratégico (Bloques A→B→C→D).

> Las dos auditorías previas en `doc/AUDITORIA_CONCURSO_MTP.md` (2026-06-19, pre-pivote) y `docs/auditoria/2026-06-25-auditoria-profunda.md` (técnica, post-F5) siguen siendo el marco. Esta se centra **solo** en lo que falta para el concurso y NO repite los hallazgos técnicos (RLS, atomicidad, etc.) salvo donde tocan la demo.

---

## 1. Veredicto

**Mnemo está en camino de ganar, pero hoy NO está listo para la demo, y la brecha es de "última milla", no de motor.** El backend del motor + la IA están **construidos y probados** (585 funciones de test, 17 migraciones, certificado Ed25519 con `verify`, `self_eval` poblado y degradable, reporter de Playwright real con captura de DOM). Lo que decide el premio —la **demo de 3 actos ejecutable e2e**, la **ROI en pantalla**, el **PDF del certificado** y el **aislamiento A/B demostrable**— **no existe todavía como experiencia mostrable de un tirón**. Ninguna pieza requiere I+D nueva: son **plumbing + datos de demo + presentación**.

**La distancia a "ganador" es corta y de bajo riesgo técnico**, pero **NO es trivial** y hay **dos showstoppers concretos** que hoy rompen el "una sola pasada":

1. 🔴 **El `docker_init.py` de la demo on-prem solo aplica las migraciones 001–006** (`scripts/docker_init.py:21-28`). Las tablas de Autopilot (triaje 009, acciones 010, certificados 014, correcciones 015, hardening 016, materializing 017) **no se crean** → `docker compose up` levanta un sistema **sin el motor que se va a presentar**. La demo dockerizada (el "un comando" del `DEMO.md`) **no arranca el producto del pitch hoy.**
2. 🔴 **El webhook de CI no publica el gate ni emite certificado automáticamente** (`src/api_v2.py:479-515`): ingesta + triaje sí, pero "push → gate rojo automático" del Acto 1 **requiere llamadas manuales** a `POST /v2/gate/run/{id}` y a la emisión del certificado. (D3 de la auditoría previa: **sigue abierto**.)

A esto se suma que **la ROI en pantalla no existe** (cero referencias a ahorro/coste/€ en el frontend), **el PDF del certificado no existe** (solo HTML; no hay librería PDF en `requirements.txt`), y **el seed no produce los 3 escenarios** (real→rojo / mantenimiento+DOM→self-heal / flaky→verde): siembra Allure legacy en **una sola org**, sin DOM y sin segunda org para el A/B.

**Lectura de probabilidad:** con ~18 semanas y el motor ya hecho, **cerrar el Bloque C es muy alcanzable** (estimo 4–6 semanas de trabajo enfocado para una demo sólida e2e, dejando holgura). El riesgo real **no es técnico, es de foco**: si el tiempo se va en más features de motor (Bloque B+) en vez de en la demo (Bloque C), se llega a octubre con un backend excelente que **nadie sabrá ver en 10 minutos**. El segundo riesgo, **mayor y externo**, es la **elegibilidad/IP (base 11)**: si MTP se queda los derechos de explotación, la tesis "Vía B" (reventa del certificado) se cae — hay que **confirmarlo antes de invertir en el pitch de monetización**.

**Camino crítico (1 línea):** demo dockerizada que arranque el motor (fix migraciones) → webhook que auto-publique gate+cert → 3 artefactos de seed (rojo/self-heal/verde) + 2ª org → ROI en pantalla → PDF del cert → guion + ensayo.

---

## 2. Construido vs. necesario (inventario)

### 2.1. Lo construido (verificado en el repo)

| Pieza | Estado | Evidencia |
|---|---|---|
| Motor de triaje determinista R0–R6 | ✅ Construido y probado | `src/triage/engine.py:19-49`; registra `rule_applied` y `llm_assisted` (`db/migrations/009_triage.sql:15,18`) |
| Ingesta CI (webhook HMAC) + Allure/JUnit | ✅ Construido | `src/api_v2.py:479-515`; `verify_signature` (`src/ci/webhook_auth.py`) |
| **Reporter de Playwright (npm)** | ✅ **Existe** (resuelve D1) | `packages/mnemo-playwright-reporter/src/*` (242 líneas + 5 test files); captura DOM (`reporter.ts:37-48`, `fixture.ts`, `artifact.ts:13`) y la envía (`post.ts`) |
| Acción Nivel-2 (self-heal / quarantine / ticket) + approve humano | ✅ Construido | `src/actions/`; `SelfHealActuator` requiere `green_dom`+`failure_dom` (`src/actions/selfheal/selfheal.py:37-38`) |
| Atomicidad approve→materialize | ✅ Resuelto (B2) | migración `017_actions_materializing.sql` (estado intermedio) |
| Certificado de release v2 + firma Ed25519 + **verify** | ✅ Construido | `src/certify/certificate.py:104-118`; firma `src/certify/signing.py:18-22`; verify `signing.py:25-31`; endpoint `POST /v2/certificates/verify` (`api_v2.py:890-900`) |
| **`self_eval` poblado** (calibración + composición + `ai_eval` LLM-judge) | ✅ Construido y degradable | `certificate.py:31-52`; LLM-judge `src/certify/service.py:35-40` (degrada a `ai_eval=None`); baja confianza si faithfulness<0.5 (`certificate.py:38-39`) |
| Gate de release (rojo/verde) | ✅ Construido | `src/certify/gate.py:25-33`; endpoint `POST /v2/gate/run/{id}` (`api_v2.py:903-910`) |
| Lazo de aprendizaje / foso (calibración por cliente) | ✅ Construido | métricas `get_calibration_metrics`; UI `frontend/src/app/app/calibration/page.tsx` |
| **Frontend completo (9 páginas)** | ✅ Construido | `frontend/src/app/app/{autopilot,defects,assurance,calibration,knowledge,integrations,org,settings,analyze}/page.tsx` |
| Run view de Autopilot (4 tarjetas) | ✅ Construido | `frontend/src/components/autopilot/{RunSelector,TriageVerdictList,ActionsPanel,CertificateCard,GateCard}.tsx` |
| Briefing del run (IA, agregación citable) — B5 | ✅ Construido | `GET /v2/runs/{id}/briefing`; `src/ai/` |
| RAG NL sobre Defect DNA con citas — B3 | ✅ Construido | `POST /v2/defects/ask` |
| Coste API = 0€ **por diseño** (Ollama local + HF embeddings + guard) | ✅ Arquitectónico | default `ollama` (`src/config.py:13`); guard `ALLOW_EXTERNAL_LLM` (`src/llm/factory.py:20-24`); embeddings locales (`src/defects/embedder.py`) |
| CI backend (unit + AI-eval golden) | ✅ Parcial | `.github/workflows/backend-ci.yml`: pytest `not integration` + `eval_ai.py --min-accuracy 0.8` (golden de 10 casos) |
| docker-compose stack completo | ✅ Existe (con bug, ver 2.2) | `docker-compose.yml`: db, auth, kong, ollama, backend, frontend, init |

### 2.2. Lo que falta para una demo ganadora (la brecha real)

| Necesario (Bloque C/D) | Estado | Evidencia / por qué |
|---|---|---|
| 🔴 **Demo dockerizada que arranque el motor** | **ROTO** | `scripts/docker_init.py:21-28` aplica solo migraciones **001–006**; faltan 007–017 → sin tablas de triaje/acciones/certificados. `docker compose up` ≠ producto del pitch. |
| 🔴 **"Push → gate rojo automático" (Acto 1 e2e)** | **MANUAL** (D3 abierto) | `api_v2.py:479-515`: el webhook ingesta+triaja pero **no** llama `publish` del gate ni emite certificado. Hay que invocar `POST /v2/gate/run/{id}` a mano. |
| 🔴 **Seed con 3 escenarios + 2ª org** | **NO** (D2 abierto) | `docker_init.py:97-115` siembra Allure legacy (sin DOM) en **una** org "Demo MTP". Sin DOM → `SelfHealActuator` devuelve `None` → **no hay PR** (Acto 2). Sin 2ª org → no hay A/B. |
| 🟠 **ROI en pantalla** (Bloque C + métrica Bloque D) | **NO existe** | Cero matches de `ROI`/`ahorro`/`coste`/`€`/`saved` en `frontend/src`. Calibration muestra precisión, no ahorro. |
| 🟠 **PDF del certificado** (entregable facturable) | **NO** (solo HTML) | `src/certify/render.py` genera HTML; `GET /v2/certificates/{id}/html`. Sin librería PDF en `requirements.txt` (hay `pypdf` pero es para *leer*). |
| 🟠 **Descarga del certificado en la UI** | **NO** | `CertificateCard.tsx:43` muestra los 32 primeros chars de la firma; sin botón de descarga/exportar. |
| 🟠 **Guion de 3 actos + runbook** (D4 abierto) | **NO** | `legacy/DEMO.md` describe el producto **anterior** (Defect DNA + causa raíz); `scripts/smoke_demo.sh` solo verifica health/login. No hay runbook "Acto 1→2→3". |
| 🟡 **% auto-triaje como métrica agregada** (Bloque D) | **MEDIBLE, sin superficie** | El dato está por-run en el certificado (`run_composition`: total/deterministic/llm_assisted, `certificate.py:47`) y por-verdicto (`llm_assisted`). Falta un endpoint/panel que lo agregue por org/periodo. |
| 🟡 **Sign-offs ricos en el certificado** | **NO** (sigue `[]`) | `service.py:44` pasa `sign_offs=[]`; `approved_by`/`approved_at` existen en acciones pero no se vuelcan al certificado. |
| 🟡 **Momento "wow" verify limpio** | **PARCIAL** | `POST /v2/certificates/verify` exige `Depends(get_current_user)` (`api_v2.py:893`) → el "modifico 1 byte → `valido:false`" necesita sesión logueada; no hay CLI/endpoint público para el gesto en vivo. |

---

## 3. Bloque C (demo del concurso) — descompuesto

El Bloque C son **4 entregables**: (1) los 3 actos e2e, (2) ROI en pantalla, (3) PDF del certificado, (4) aislamiento org A/B en vivo. Esfuerzo: **S**<½d · **M** 1-3d · **L** 1-2 sem. Lo marcado 🔴 es **camino crítico** (sin ello no hay demo).

### C1 — Los 3 actos ejecutables e2e (🔴 camino crítico)

**Acto 1 — push → gate rojo automático.** Hoy roto por dos cosas:
- **C1a (🔴, S):** arreglar `docker_init.py` para aplicar **todas** las migraciones (001–017), no solo 001–006. *Sin esto nada del motor existe en la demo dockerizada.* Es el fix de mayor retorno y menor esfuerzo del informe.
- **C1b (🔴, S-M):** que el `ci_webhook` llame a `get_gate_service().publish(...)` (y emita el certificado) tras el triaje, degradando si GitHub no está configurado (`api_v2.py:515`). ~5–15 líneas. Cierra "push → rojo".

**Acto 2 — acción Nivel-2 (self-heal PR) con approve humano.** El backend y la UI (`ActionsPanel`) están; el bloqueo es **el dato**:
- **C1c (🔴, M):** seed que incluya un artefacto CI **formato Playwright con DOM** (`dom.last_green` + `dom.failure`) para un fallo de **mantenimiento** (locator roto) → `SelfHealActuator` produce parche/PR. Sin DOM, devuelve `None` y **no hay Acto 2**. Idealmente, además, un GitHub App de demo (o un modo "PR simulado" que no requiera App viva — ver Riesgos).

**Acto 3 — certificado firmado + verify.** Funciona ya (emisión + `verify`); pulir el gesto:
- **C1d (S):** el "wow" del verify en vivo. O bien un pequeño CLI/script que verifique un cert exportado (cert válido→`true`, flip 1 byte→`false`) sin auth, o bien hacerlo desde la UI con la sesión ya abierta. Hoy el endpoint exige token (`api_v2.py:893`).

### C2 — ROI en pantalla (🟠 alto impacto, no bloqueante del flujo)
- **C2 (M):** una tarjeta de ROI en el run view / un panel de release: tiempo ahorrado estimado (nº de triajes automáticos × minutos/triaje manual), coste API del release (≈0€ por diseño), nº de defectos agrupados reusados. Los **inputs existen** (`run_composition`, `llm_assisted`, familias); falta la fórmula + el componente. Es lo que convierte "herramienta" en "negocio" ante el jurado.

### C3 — PDF del certificado (🟠 entregable facturable)
- **C3 (M):** añadir render PDF (p.ej. `weasyprint` sobre el HTML ya existente de `render.py`, o `reportlab`) + endpoint `GET /v2/certificates/{id}/pdf` + botón de descarga en `CertificateCard`. Es el artefacto que el jurado se lleva y el "wow" de cierre.

### C4 — Aislamiento org A/B en vivo (🟠 diferenciador de seguridad)
- **C4a (S):** seed de **dos** orgs (A y B) con dos usuarios; hoy `docker_init.py` crea una sola ("Demo MTP").
- **C4b (S):** guion que muestre que el usuario de A no ve los datos de B (la UI ya soporta selector de org en `defects`/`calibration`; el backend ya filtra por membership en cada repo). La frase "user_b no ve la org de A" es ganadora; el código ya lo garantiza, falta **demostrarlo en pantalla**.

### ¿Qué es realista en ~4 meses?
**Todo el Bloque C, con holgura.** C1a/C1b/C4a/C4b son S (días). C1c/C2/C3 son M (1-3 días c/u). Ninguno es I+D. Estimación agregada: **3–5 semanas** de trabajo enfocado para tener la demo e2e sólida + ensayada, dejando ~12 semanas de colchón para el pitch (Bloque D), pulido y contingencias. **El camino crítico es C1 (los 3 actos)**; C2/C3/C4 lo refuerzan pero no lo bloquean.

---

## 4. Bloque D (pitch) — ¿se pueden instrumentar las 3 métricas?

| Métrica | ¿Medible hoy? | Detalle / evidencia |
|---|---|---|
| **% auto-triaje** | 🟡 **Medible, falta superficie agregada** | El motor registra `llm_assisted` por verdicto (`009_triage.sql:18`) y `rule_applied` R0–R6 (`:15`); R0–R5 = determinista, R6 = LLM (`triage/engine.py:19-49`). Por-run ya se atestigua en el certificado (`run_composition`, `certificate.py:47`). **Falta** un `GET /v2/metrics/...` o panel que haga `count(llm_assisted=false)/count(*)` por org/periodo. Esfuerzo S-M. **Esta métrica es sólida y honesta** (sale del dato firmado). |
| **Coste API ~0€/release** | 🟡 **Verdadero por arquitectura, NO instrumentado** | Default Ollama local (`config.py:13`), embeddings HF locales (`embedder.py`), guard `ALLOW_EXTERNAL_LLM` (`factory.py:20-24`). **Cero** token-counting/telemetría de coste (sin `tiktoken`/`usage`/`cost` en `src/`). Se puede **afirmar** "0€ por diseño" con evidencia de configuración, pero **no presentar un número medido**. Para el pitch basta el argumento arquitectónico; si se quiere un gráfico, hay que instrumentar (o calcular el contrafactual "qué costaría con GPT-4: N tokens × $/token"). |
| **Re-rating del múltiplo (1-2× → 8-15×)** | ⚪ **No está en código** (correcto) | Métrica de negocio/valoración; no pertenece al repo. Va en el pitch, no se instrumenta. |

**Telemetría general:** **no hay** Prometheus/OTel/statsd/PostHog ni emisión de métricas en el backend. Para el concurso no es imprescindible (las dos métricas técnicas se derivan del dato firmado), pero un panel de tendencias (ya sugerido en la auditoría del 25) elevaría "Impacto" y daría el gráfico del pitch.

**Conclusión Bloque D:** las **3 métricas son defendibles**. La (% auto-triaje) es la más fuerte porque **emana del certificado firmado** (no es marketing). La (coste 0€) es honesta como propiedad arquitectónica; conviene **no sobre-vender** un "número medido" que no existe. La (múltiplo) es narrativa pura.

---

## 5. Riesgos de entrega (qué podría descarrilar la demo)

Priorizados por probabilidad × impacto sobre la demo en vivo:

1. 🔴 **#1 — La demo dockerizada no arranca el motor (migraciones 001-006).** Es el riesgo más alto y más barato de eliminar: si el jurado hace `docker compose up` (como hizo en la auditoría de junio con el producto viejo), ve un sistema sin Autopilot. **Mitigación:** C1a (S). **Hasta arreglarlo, la demo "un comando" es una trampa.**
2. 🔴 **#2 — Dependencia de un GitHub App real/vivo para el Acto 2.** El self-heal "produce un PR" necesita una installation de GitHub App configurada y operativa **durante la demo** (red, credenciales, repo). Una demo en vivo que depende de un servicio externo es frágil. **Mitigación:** preparar un repo de demo + App con antelación **y** tener un "modo demo" que muestre el artefacto/PR-diff sin requerir la App viva (o un PR ya creado y enlazado). No dejar esto para octubre.
3. 🟠 **#3 — Ollama local en vivo (latencia/arranque del modelo).** El desempate LLM (R6), la causa raíz, el briefing y el `ai_eval` usan DeepSeek-R1:8B local. En vivo: descarga de ~5GB (una vez), RAM, latencia de 1ª inferencia. Si el modelo no está caliente, el Acto se cuelga. **Mitigación:** pre-cachear el modelo, calentar antes de la demo, y apoyarse en que **todo degrada con elegancia** (el cert se emite con `ai_eval=None`; el flujo determinista no depende del LLM). Ensayar el camino determinista como plan B.
4. 🟠 **#4 — Datos de demo no deterministas / seed frágil.** El seed actual no produce los 3 escenarios y depende de descargar embeddings HF en la 1ª ejecución (lento). Una demo sin datos pre-fabricados reproducibles es una ruleta. **Mitigación:** C1c + C4a con artefactos **fijos y versionados**, y pre-warm de embeddings.
5. 🟠 **#5 — Integración corre contra PROD sin rollback (riesgo de datos).** 15 ficheros de test de integración contra la BD prod (`nevgshcuhjaanugddfcv`, según memoria del proyecto) sin `BEGIN/ROLLBACK`. No rompe la demo, pero es un riesgo operativo y una **red flag si el jurado lo ve**. **Mitigación:** BD de test dedicada (ya señalado como M6 en la auditoría del 25).
6. 🟡 **#6 — El "wow" del verify exige login.** Menor, pero el gesto más memorable (flip 1 byte) hoy necesita sesión. **Mitigación:** C1d (script/CLI sin auth, o hacerlo con la sesión abierta).
7. 🟡 **#7 — CI sin gate de cobertura ni integración.** El jurado es una **empresa de testing**: que el CI corra solo unit + un golden de 10 casos, sin coverage threshold ni integración, es atacable. **Mitigación:** añadir threshold de cobertura y, si se puede, integración en CI contra BD efímera.

---

## 6. Elegibilidad / IP — PREGUNTA ABIERTA CRÍTICA (base 11)

> ⚠️ **Esto no está en el repo y es la decisión de mayor palanca del proyecto. Debe confirmarlo el usuario ANTES de invertir en el pitch de monetización.**

- **Riesgo (base 11 — cesión de derechos):** según el análisis de vendibilidad y la nota de la auditoría del 19-jun (`doc/AUDITORIA_CONCURSO_MTP.md` §8), **participar podría ceder a MTP los derechos de explotación de lo presentado**. Si así fuera, **choca de frente con la tesis "Vía B"** (reventar el certificado de release firmado como producto/servicio): no se puede vender lo que ya cediste.
- **Por qué es crítico ahora:** el Bloque D del plan estratégico **vende precisamente la monetización** (re-rating del múltiplo, certificado como producto). Si la base 11 cede la IP, **el pitch de valoración hay que reescribirlo** (de "producto vendible" a, p.ej., "herramienta interna de MTP que multiplica su capacidad"), que sigue siendo ganador para el premio pero **cambia la narrativa de cierre**.
- **Elegibilidad de participación:** el concurso está restringido a integrantes de MTP España/México/Brasil, LAUDE, LAUDE Canarias o APARA (`doc/AUDITORIA_CONCURSO_MTP.md` §8). **Confirmar pertenencia** antes de cualquier inversión adicional.

**Acción para el usuario (bloqueante de la estrategia de pitch):**
1. Leer la **base 11 literal** del reglamento del MTP AI Innovation Award.
2. Determinar: ¿la cesión es de los *derechos de explotación* o solo una licencia de uso/exhibición? ¿Aplica a todo lo "presentado" o solo al material del concurso?
3. Según la respuesta, **elegir la narrativa de valoración del Bloque D** (Vía B reventa vs. valor interno MTP). No construir el deck de monetización hasta resolverlo.

---

## 7. Secuencia recomendada (~18 semanas)

Orden por dependencia y retorno. Los hitos 🔴 son el camino crítico para que **exista** una demo; el resto la hace **ganadora**.

**Fase 0 — Desbloqueo (semana 0, en paralelo, antes de programar):**
- **[Usuario] Resolver base 11 (§6)** — decide la narrativa del Bloque D. *Bloqueante de la estrategia, no del código.*

**Fase 1 — "Que la demo exista e2e" (semanas 1–2) · 🔴 imprescindible:**
- **C1a (S):** `docker_init.py` aplica migraciones 001–017. *(Mayor retorno/esfuerzo del informe.)*
- **C1b (S-M):** `ci_webhook` auto-publica gate + emite certificado (degradable). Cierra Acto 1.
- **C1c (M):** seed con 3 artefactos fijos (real→rojo / mantenimiento+DOM→self-heal / flaky→verde). Desbloquea Acto 2.
- **C4a (S):** seed de 2ª org + usuario. Desbloquea A/B.
- *Hito: los 3 actos corren de principio a fin con datos reproducibles.*

**Fase 2 — "Que la demo gane" (semanas 3–6) · 🟠 alto impacto:**
- **C3 (M):** PDF del certificado + descarga en UI (el "wow" de cierre, entregable facturable).
- **C2 (M):** ROI en pantalla (tarjeta de tiempo/coste ahorrado del release).
- **C1d (S):** gesto del verify en vivo (script sin auth o desde sesión).
- **C4b (S):** guion del A/B en pantalla.
- **% auto-triaje agregado (S-M):** endpoint/panel para la métrica del pitch.
- **D4 (S-M):** reescribir `DEMO.md` como runbook de 3 actos + setup del GitHub App de demo (con modo "PR simulado" de respaldo, riesgo #2).

**Fase 3 — "Endurecer para el jurado de QA" (semanas 7–9) · 🟠 credibilidad:**
- Mitigar riesgo #5 (integración fuera de prod) y #7 (coverage gate + integración en CI). El jurado es una empresa de testing: el CI honesto suma.
- Sign-offs ricos en el certificado (vuelca `approved_by`/`approved_at`).
- Pre-warm de Ollama/embeddings y ensayo del plan B determinista (riesgo #3/#4).

**Fase 4 — Pitch + ensayo (semanas 10–14) · Bloque D:**
- Deck con las 3 métricas (% auto-triaje del cert firmado, 0€ por diseño, múltiplo) y la narrativa de valoración **según el resultado de Fase 0**.
- Categoría "Release Assurance Autopilot". Dossier (equipo, proyecto, solución con MVP operativo).
- **Ensayar la demo en vivo ≥3 veces** end-to-end, cronometrada, con el plan B.

**Colchón (semanas 15–18):** contingencia, pulido, segunda ronda de ensayo. *Que exista colchón es la señal de que el plan es realista.*

---

## Apéndice — Evidencia clave (archivo:línea)

- Migraciones incompletas en demo: `scripts/docker_init.py:21-28` (solo 001-006) y `:97-115` (seed 1 org, Allure sin DOM).
- Webhook sin auto-gate/cert: `src/api_v2.py:479-515`.
- Certificado v2 + firma + verify: `src/certify/certificate.py:104-118`; `src/certify/signing.py:18-31`; `src/api_v2.py:890-900` (verify con `Depends(get_current_user)` en `:893`).
- `self_eval` poblado + LLM-judge degradable: `src/certify/certificate.py:31-52`; `src/certify/service.py:35-44` (sign_offs=[] en `:44`).
- Render solo HTML, sin PDF: `src/certify/render.py`; `requirements.txt` (sin weasyprint/reportlab; `pypdf` solo lee).
- Reporter de Playwright real con DOM: `packages/mnemo-playwright-reporter/src/reporter.ts:37-48`, `fixture.ts`, `artifact.ts:13`, `post.ts`.
- Self-heal requiere DOM: `src/actions/selfheal/selfheal.py:37-38`.
- % auto-triaje (dato existe): `db/migrations/009_triage.sql:15,18`; `src/triage/engine.py:19-49`; `src/certify/certificate.py:47`.
- Coste 0€ por diseño (sin instrumentar): `src/config.py:13`; `src/llm/factory.py:20-24`; `src/defects/embedder.py`.
- ROI ausente en UI: cero matches `ROI`/`ahorro`/`coste`/`€` en `frontend/src`.
- Run view (4 tarjetas): `frontend/src/components/autopilot/{RunSelector,TriageVerdictList,ActionsPanel,CertificateCard,GateCard}.tsx`; `CertificateCard.tsx:43` (firma truncada, sin descarga).
- CI backend: `.github/workflows/backend-ci.yml` (unit + `eval_ai.py --min-accuracy 0.8`; sin integración ni coverage gate).
- Elegibilidad/IP: `doc/AUDITORIA_CONCURSO_MTP.md` §8 (base 11 + restricción de participantes).
