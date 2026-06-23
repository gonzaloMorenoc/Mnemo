# Spec — Mnemo Autopilot: el ingeniero de QA autónomo (motor agéntico + certificación)

**Fecha:** 2026-06-22
**Rama:** `feat/mnemo-autopilot` (desde `main`)
**Nombre de producto:** **Mnemo Autopilot** (el motor agéntico sobre la memoria de Mnemo)
**Contexto:** ampliación estratégica de Mnemo. La base actual (ingesta Allure/JUnit → fingerprint → Defect DNA → veredicto) está construida (`docs/superpowers/specs/2026-06-20-mnemo-assurance-platform-design.md`). Esta spec define el salto de "memoria pasiva" a "agente que actúa". Plazo del MTP AI Innovation Award: 30-oct-2026.
**Capacidad asumida:** un desarrollador con dedicación fuerte + apoyo de agentes.

---

## 1. Tesis de valor (por qué esto vale millones)

Una consultora de testing (MTP) gana dinero con **horas facturables de ingenieros de QA**: `facturación = nº ingenieros × utilización × tarifa`. Un panel que agrupa fallos no mueve ninguna de esas variables — es una *feature*, no un *producto*. Y en 2026 la IA amenaza el modelo: si la IA tria, escribe y mantiene tests, el negocio "vender cabezas" se erosiona.

Lo que una consultora paga a precio de millones hace una de estas tres cosas (idealmente las tres):
1. **El mismo trabajo con muchas menos horas sénior** → margen.
2. **Ganar más licitaciones / vender más proyectos** → diferenciador comercial.
3. **Convertir servicios en producto recurrente** → multiplica la valoración (SaaS 8-15× ingresos vs. consultora 1-2×).

**El giro central:** el Defect DNA no es el producto, es el **combustible**. El producto es un **agente que usa esa memoria para hacer el trabajo que hoy se factura por horas**. Mnemo hoy es "un sitio al que subes fallos"; eso pierde (lo dice el propio ADR: "una herramienta a la que vas pierde frente a inteligencia que viene a ti"). Mnemo Autopilot es **inteligencia enganchada al CI del cliente** que decide, actúa y certifica.

**Pitch en una frase:**
> *"Mnemo Autopilot: el copiloto de QA que se engancha a tu CI, decide solo si cada fallo es bug real, flaky o test roto, propone el arreglo, y firma un certificado auditable de si el release es apto — todo privado, on-premise, coste de API 0 €."*

## 2. Objetivo y no-objetivos

**Objetivo (este spec):** un **slice vertical e2e demo-able** que cuente la historia "motor + envoltorio" completa:

**CI en vivo (GitHub Actions) → triaje autónomo de cada fallo → acción Nivel 2 (self-heal del locator en PR borrador / cuarentena con deuda / ticket enriquecido) → gate en CI + Release Assurance Certificate firmado → lazo de aprendizaje por tenant.**

**No-objetivos (roadmap narrado, no se construye en este slice):**
- Conectores Jira / Azure DevOps (la interfaz queda lista; se implementa **solo GitHub**).
- Self-heal para Selenium/Java y Cypress (se implementa **solo el caso común de locator Playwright/TS**).
- Testing predictivo / por riesgo (dirección B).
- PKI/sigstore completo (se hace firma Ed25519 simple).
- Clasificador entrenado (Opción 3); el lazo de aprendizaje **pavimenta** su dataset, no lo entrena aún.
- Empaquetado del appliance air-gapped (se documenta como argumento; no se empaqueta).
- Auto-merge de fixes (Nivel 3); el diseño es **Nivel 2: humano aprueba siempre**.

## 3. Decisión arquitectónica de fondo: el cerebro determinista-primero

El clasificador de triaje se construye **determinista-primero, LLM de apoyo** (Opción 1 de tres evaluadas), y no por preferencia:

- **No se puede certificar sobre una caja negra que alucina.** El producto de certificación (C) **exige** que el veredicto sea explicable y reproducible. El determinista emite una traza de "por qué decidí esto" que firma un auditor. Un agente LLM-primero (Opción 2) lo haría imposible.
- **Eficiencia (20% del concurso):** ingesta barata (señales + SQL); el LLM local solo entra en la narrativa y en los casos ambiguos. Coherente con la arquitectura actual (funciones puras + LLM perezoso).
- **Anti-alucinación = meta-mensaje:** "una herramienta de Assurance cuyo propio motor es determinista y auditable, y que además se auto-evalúa con RAGAS".
- **Reutiliza lo existente:** `fingerprint.py`, `match.py`, `centroid.py`, `verdict.py` ya son funciones puras. El cerebro es **una capa de reglas + retrieval encima**.

Alternativas descartadas: **Opción 2 (LLM-primero)** — flexible pero lenta, alucina y no es auditable. **Opción 3 (clasificador entrenado)** — mejor a largo plazo pero no hay datos etiquetados todavía (prematuro); el lazo de aprendizaje los acumula.

## 4. Arquitectura — la espina dorsal (5 etapas)

```
  Repo de demo (Playwright/TS) ──push──► GitHub Actions corre los tests
        │                                         │ run termina (verde/rojo)
        │                                         ▼
        │           ① INGESTA VIVA → POST /v2/ci/webhook  (reusa la ingesta + commit SHA + pass)
        │                                         │  reporter Playwright → artefacto enriquecido
        │                                         ▼
        │           ② TRIAJE (determinista + DNA, desempate LLM):
        │                  cada fallo → {categoría, confianza, evidence_bundle}
        │                  · defecto real · flaky conocido · mantenimiento · infra
        │                                         ▼
        │           ③ ACCIÓN (Nivel 2, humano aprueba — actuadores intercambiables):
        ├──GitHub App (PR borrador)◄─── mantenimiento → self-heal del locator → PR
        │                                  flaky → cuarentena + ticket de deuda
        │                                  defecto real → ticket enriquecido (root-cause + linaje)
        │                                         ▼
        │           ④ CERTIFICA:
        └──check run (gate)◄──────────── build_verdict → risk score → aprueba/bloquea deploy
                                          + Release Assurance Certificate firmado (JSON+HTML, Ed25519)
                                                  ▼
                                   ⑤ APRENDE: humano confirma/corrige → ajusta umbrales + DNA (por tenant)
```

**Dónde vive cada cosa (con Vercel + Supabase):**

```
  Vercel (Next.js) — solo cliente:           Backend (infra del cliente) — el foso:
   · Bandeja de aprobación Nivel 2            · FastAPI /v2 + triaje + actuadores
   · Vista del certificado (HTML)             · LLM local (Ollama) + embeddings (HF)
   · Dashboard ejecutivo de Assurance         · Supabase (Postgres+pgvector, Auth, Storage, Realtime)
        │  HTTPS → API del cliente            · Firma Ed25519 (clave privada local)
        └───────────────────────────────────►· GitHub App (PR/issues/checks)
```

**Principio:** el frontend (Vercel) es **solo cliente**; datos, LLM y firma viven en el backend del cliente. Una sola base de código, dos modos de despliegue (§12).

## 5. El motor de triaje (componente nuevo, núcleo del valor)

Por cada fallo de un run, emite **`{categoría, confianza, evidence_bundle}`** de forma determinista y auditable.

### 5.1. Taxonomía y señales (objetivas)

| Categoría | Significado | Señales que la disparan | Acción (§6) |
|---|---|---|---|
| **Flaky conocido** | Test no determinista; mismo código pasa y falla | **(oro)** pasó al reintentar en el *mismo* run · historial pass+fail sobre el *mismo* commit SHA · match de fingerprint a familia ya etiquetada flaky | Cuarentena + retry |
| **Mantenimiento** | El producto cambió legítimamente y el test no se actualizó | error de *locator* (`locator not found`, `strict mode violation`, `not visible`) · el DOM del elemento cambió vs. último run verde · **el código del test NO cambió** | **Self-heal → PR borrador** |
| **Defecto real** | El test cazó un bug genuino del producto | fallo de aserción (`expect(...)`) · fingerprint novedoso · el test no cambió de intención | Ticket enriquecido |
| **Infra/entorno** | Fallo del entorno, no del producto ni del test | `ECONNREFUSED`/`net::ERR`/timeout de red · crash de navegador · **co-fallo masivo** con misma firma | Marcar + reintentar |

### 5.2. Lógica de decisión (determinista, por prioridad)

```
1. ¿pasó al reintentar  OR  historial intermitente mismo-SHA?   → FLAKY        (conf. alta)
2. ¿co-fallo masivo con firma de infra?                          → INFRA        (conf. alta)
3. ¿error de locator  AND  DOM cambió  AND  test sin cambios?    → MANTENIMIENTO(conf. alta)
4. ¿aserción fallida  AND  fingerprint novedoso?                 → DEFECTO REAL (conf. media-alta)
5. señales en conflicto / por debajo de umbral                  → DESEMPATE LLM (conf. ≤ 0.7,
                                                                    marcado "LLM-assisted")
```

### 5.3. Confianza y papel del LLM

- **Reglas deterministas** → confianza 0.85–0.99, sin LLM en el camino crítico.
- **Desempate LLM** (solo ambiguos) → confianza **capada a 0.7**, siempre marcado para revisión humana. El LLM recibe el `evidence_bundle` y devuelve categoría + razón; nunca decide a ciegas.
- La confianza activa el **human-in-the-loop de Nivel 2**: por debajo de umbral, el artefacto se genera pero **exige aprobación explícita**.

### 5.4. El evidence bundle (lo que se firma)

```json
{
  "fingerprint": "…", "familia_match": "id", "linaje_cross_proyecto": ["proj-x","proj-y"],
  "error_type": "locator_not_found",
  "senales_disparadas": [{"nombre":"dom_changed","valor":true},{"nombre":"test_unchanged","valor":true}],
  "regla_aplicada": "R3_dom_changed",
  "categoria": "mantenimiento", "confianza": 0.93, "requiere_aprobacion": false,
  "accion_propuesta": {"tipo":"self_heal","ref":"PR#123"}
}
```

Esta traza convierte el veredicto en **certificable** (un auditor ve el "por qué", sin caja negra) y es la entrada de la auto-evaluación RAGAS.

### 5.5. Dependencias de datos honestas

- Señal "DOM cambió" → necesita guardar un **snapshot del DOM del último run verde** por test (lo emite el reporter de Playwright; §6.4). Estado nuevo (`dom_snapshots`).
- "Historial intermitente mismo-SHA" → necesita registrar **resultados por test y por commit** (también los *pass*, no solo fallos). Cambio pequeño pero real en la ingesta (`test_results`).

## 6. La capa de acción (actuadores Nivel 2)

Cada categoría dispara un **actuador** detrás de una interfaz común (`Actuator`: `{verdicto, evidence_bundle} → artefacto en estado propuesto + registro`). Todo en estado *propuesto*; **nunca se finaliza sin aprobación humana**.

### 6.1. Self-heal del locator → PR borrador (el "wow")

Flujo **candidatos deterministas + LLM para el diff mínimo**:

```
1. Localizar el locator roto      → del error de Playwright: selector + fichero:línea.
2. Recuperar el elemento "viejo"   → atributos estables del snapshot DOM verde (texto, role,
                                     data-testid, aria-label, anclas vecinas).
3. Generar candidatos en DOM nuevo → el elemento que mejor casa esa semántica; rankear por
                                     ROBUSTEZ (getByRole > getByTestId > getByText > CSS/XPath).
4. LLM (local) produce el EDIT mínimo → reemplaza el locator + explica; ve candidatos+evidencia.
5. GitHub App abre PR BORRADOR     → diff de 1-pocas líneas; cuerpo = evidence_bundle + antes/
                                     después + confianza + "requiere revisión". NUNCA auto-merge.
```

Diferenciador: no solo arregla, **mejora** hacia un locator resiliente → el test queda **menos frágil que antes** ("no parcheamos, reducimos deuda"). Alcance MVP: selector roto por cambio de atributo/texto/estructura → locator robusto. Page Objects / multi-fichero = roadmap.

### 6.2. Flaky → cuarentena con deuda (no esconder bugs)

Como PR borrador + ticket: anotar el test (`test.fixme`/tag `@flaky`/lista de cuarentena) + retry sugerido, **siempre** con *ticket de deuda* asociado (cuarentena sin ticket = ocultar fallos). Registra la familia flaky en el DNA → próxima vez instantáneo, sin LLM.

### 6.3. Defecto real → ticket enriquecido (aquí paga el DNA)

Ticket con: hipótesis de root-cause (LLM anclado en defectos pasados *recuperados*, no inventado) + **linaje cross-proyecto** ("esta familia ya apareció en X e Y; así se resolvió") + si hay hermano resuelto, **sugiere el fix que funcionó** + severidad/riesgo del veredicto. Sink demo: **GitHub Issues**; **Jira** es un swap de interfaz (roadmap).

### 6.4. El reporter de Playwright (punto de integración)

Paquete npm fino **`mnemo-playwright-reporter`** que el repo del cliente instala. En cada test emite un **artefacto enriquecido**: contexto del fallo (selector, fichero:línea), **snapshot del DOM** (verde → "último bueno"; rojo → "actual"), estado de retry/flaky y el **commit SHA**. Lo sube como artefacto de CI / lo postea al webhook. Es lo que hace la ingesta rica y el self-heal posible.

### 6.5. La GitHub App (el puente, foso intacto)

Scopes mínimos: `contents:write` + `pull_requests:write` + `issues:write` + `checks:write`. Verificación HMAC del webhook (frontera de seguridad). Apunta a GitHub.com (demo) o **GitHub Enterprise self-hosted** (cliente regulado). Con el LLM local, **nada sale de la infra del cliente**.

## 7. Certificación (el entregable facturable)

### 7.1. El gate en CI (check run)

Tras ingesta→triaje→veredicto, Mnemo publica un **check run** sobre el commit/PR: `mnemo/assurance → success | failure | neutral`. Política configurable:

```
BLOQUEA si:  defecto(s) real(es) novedoso(s) de alta confianza por encima de umbral de severidad
             OR  ítems de baja confianza pendientes de aprobación humana (Nivel 2)
APRUEBA si:  todos los fallos son flaky-en-cuarentena-con-deuda  o  curados  o  infra reconocida
```

El "wow": el PR se pone rojo **porque "Mnemo decidió que hay un defecto real novedoso de riesgo alto"**, no por "fallaron tests"; al aprobar el self-heal, pasa a verde.

### 7.2. El Release Assurance Certificate (firmado, auditable, reproducible)

Por release, **JSON canónico (máquina) + HTML/PDF (humano)** con:

- **Identidad reproducible:** org, proyecto, commit SHA, run id, timestamp, versión de Mnemo + versión del modelo.
- **Veredicto:** `apto` / `apto-con-reservas` / `no-apto` + risk score.
- **Desglose:** N defectos reales (tickets), N flaky en cuarentena (deuda abierta), N curados (PRs), N infra.
- **Traza de evidencia** por fallo (el `evidence_bundle` de §5.4).
- **Firmas humanas:** quién aprobó qué ítem de baja confianza (rastro de Nivel 2).
- **Auto-evaluación:** métricas RAGAS de la narrativa.
- **Firma criptográfica:** Ed25519 desprendida sobre el JSON canónico, **clave en la infra del cliente** (nunca sale), + hash de contenido → tamper-evident; verificable con la clave pública.

Almacenamiento **append-only** (tabla inmutable + blob en Storage), recuperable por commit SHA → traza de auditoría en el tiempo.

**Por qué es el producto comercial (C):** entregable facturable por release (no informe interno); evidencia de cumplimiento para banca/salud/seguros; convierte "confía en mí" en "prueba firmada y reproducible".

## 8. El lazo de aprendizaje (el foso)

Vive en la bandeja de aprobación (Vercel). Cada confirmación/corrección humana alimenta al agente:

- **Confirma** → refuerza la etiqueta de la familia en el DNA (coste 0).
- **Corrige** → (1) re-etiqueta la familia/fallo; (2) **ajusta umbrales por tenant** (calibración privada); (3) queda como **ejemplo etiquetado** → acumula el dataset del futuro clasificador (Opción 3).
- **Señal de PRs:** self-heal mergeado refuerza la estrategia; rechazado la penaliza.

**Mecanismo:** todo son *datos* (overrides por tenant, etiquetas por familia, ajustes de umbral en `tenant_calibration`) que el triaje lee. Barato, auditable, sin reentrenar.

**Por qué es el foso:** la calibración es **por cliente y privada**. A los meses, el agente está afinado a la realidad de ese cliente → **IP irreemplazable que MTP posee y no pierde con la rotación**. Cierra el problema del ADR original (el conocimiento tribal se evapora).

## 9. Modelo de datos (migración `db/migrations/007_autopilot_ingestion.sql` y siguientes)

Sobre el esquema actual (`organizations`, `memberships`, `test_runs`, `failures`, `defect_families`, patrón RLS + filtros de membership). Embeddings `vector(384)`.

| Tabla (nueva salvo nota) | Campos clave | Supabase que aprovecha |
|---|---|---|
| `test_results` | id, run_id, org_id, test_name, status(`pass`/`fail`/`flaky`/`skipped`), retried bool, created_at | Postgres + RLS |
| `dom_snapshots` | id, org_id, project, test_name, kind(`last_green`/`failure`), content, commit_sha, created_at | F1: `content` inline; **Storage**+ref a escala |
| `triage_verdicts` | id, failure_id, org_id, categoria, confianza, regla_aplicada, evidence_bundle jsonb, requiere_aprobacion bool, llm_assisted bool, created_at | Postgres (JSONB) |
| `actions` | id, triage_verdict_id, org_id, tipo(`self_heal`/`quarantine`/`ticket`), artefacto_ref(PR/Issue url), estado(`proposed`/`approved`/`rejected`/`merged`), created_at | Postgres |
| `certificates` (append-only) | id, run_id, org_id, canonical_json jsonb, signature, verdict, risk_score, sign_offs jsonb, pdf_ref, mnemo_version, model_version, created_at | Postgres + **Storage** |
| `tenant_calibration` | id, org_id, regla, override jsonb (umbral/etiqueta), updated_at | Postgres + RLS |
| `defect_families` (extender) | + `label`(`flaky`/`real`/`maintenance`/`infra`/`unknown`) reforzado por uso | pgvector (ya) |

- **Aislamiento:** RLS por org + filtros de membership en la capa de aplicación (coherente con el ADR — el pooler hace BYPASS de RLS).
- `certificates` es **append-only** (sin UPDATE/DELETE) por integridad de auditoría.
- **F1 (implementado):** `commit_sha` se normaliza en `test_runs` (no se duplica en `test_results`; alcanzable por `run_id`). Los snapshots DOM se guardan inline (`content`) en F1; el blob en Storage es optimización a escala.
- **Pendiente F2:** la ingesta del webhook **no es atómica** (run/results/snapshots en transacciones separadas → "at-least-once"). F2 añade ingesta atómica en una transacción + **clave de idempotencia por run** (`commit_sha`+`project`) para deduplicar reintentos del CI.
- **Endurecimiento F1 (tras revisión):** el webhook acota el tamaño del cuerpo (`CI_MAX_BODY_BYTES`, 413) y los campos del artefacto (`max_length` en `dom`/`message`/`trace` + nº de tests) contra DoS por memoria; **enforce mono-org** vía `CI_SERVICE_ORG_ID` (403 si `artifact.org_id` no coincide), de modo que el secreto del CI queda ligado a un único org sin necesidad de secretos por-org (eso queda como evolución). El repositorio valida que `run_id` pertenezca al `org_id` y que `status`/`kind` sean válidos (→ 400, no 502).

## 10. Endpoints nuevos (`/v2`, con `Depends(get_current_user)` salvo el webhook)

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| POST | `/v2/ci/webhook` | payload GitHub (HMAC) + artefacto del reporter | `{run_id, triaged, gate}` |
| GET | `/v2/triage/run/{id}` | — | veredictos de triaje del run (categoría, confianza, evidencia) |
| GET | `/v2/actions` | query: `status=proposed` | bandeja de aprobación (ítems Nivel 2 pendientes) |
| POST | `/v2/actions/{id}/approve` | — | finaliza artefacto (PR ready / Issue) + registra sign-off + alimenta lazo |
| POST | `/v2/actions/{id}/reject` | `{motivo?}` | marca rechazado + penaliza estrategia |
| POST | `/v2/triage/{failure_id}/correct` | `{categoria_correcta}` | re-etiqueta + ajusta `tenant_calibration` |
| GET | `/v2/certificates/{run_id}` | — | certificado (JSON canónico + firma) |
| GET | `/v2/certificates/{run_id}/pdf` | — | render HTML/PDF |
| POST | `/v2/certificates/verify` | `{canonical_json, signature}` | `{valido: bool}` (auditor) |

El gate (check run) lo publica Mnemo **saliente** vía GitHub Checks API; no es un endpoint entrante.

Errores: auth 401, webhook HMAC inválido 401, multitenant no configurado 503, validación 422, datos malos 400, DB 502 (patrón `/v2` actual). El LLM caído degrada con elegancia (narrativa null, desempate → "requiere_aprobacion=true").

## 11. Componentes nuevos (interfaces claras, archivos pequeños <400 líneas)

| Módulo | Responsabilidad | Interfaz |
|---|---|---|
| `src/ci/github_webhook.py` | Verificar HMAC + parsear payload → contexto de run | `parse_webhook(body, sig) -> CiRunContext` |
| `src/ci/github_app.py` | Cliente GitHub App: PR borrador, Issue, check run | `CodeHost` (Protocol) + `GitHubApp` |
| `src/triage/signals.py` | Funciones puras: cada señal desde fallo + historial + DOM | `compute_signals(...) -> Signals` |
| `src/triage/engine.py` | Lógica de decisión pura (reglas por prioridad) → veredicto | `triage(signals, *, calibration, tiebreaker) -> TriageVerdict` |
| `src/triage/evidence.py` | Construir el `evidence_bundle` | `build_evidence(...) -> dict` |
| `src/heal/dom.py` | Diff de snapshots DOM + ranking de candidatos de locator | `rank_candidates(old, new) -> list[Locator]` |
| `src/actions/base.py` | Interfaz común de actuadores | `Actuator` (Protocol) |
| `src/actions/self_heal.py` | Candidatos + LLM diff → PR borrador | `SelfHealActuator` |
| `src/actions/quarantine.py` | Anotación + ticket de deuda | `QuarantineActuator` |
| `src/actions/ticket.py` | Ticket enriquecido con linaje | `TicketActuator` |
| `src/certify/certificate.py` | JSON canónico del certificado | `build_certificate(run) -> dict` |
| `src/certify/signing.py` | Firma/verificación Ed25519 | `sign(json) -> sig`, `verify(json, sig) -> bool` |
| `src/certify/render.py` | Render HTML/PDF | `render(cert) -> bytes` |
| `src/learning/calibration.py` | Overrides por tenant (lectura/escritura) | `get_calibration(org_id)`, `apply_correction(...)` |
| `src/api_v2.py` (extender) | Endpoints §10 | — |
| `mnemo-playwright-reporter` (npm) | Reporter que emite artefacto enriquecido + DOM | reporter de Playwright |

Principios: **funciones puras** (signals, engine, evidence, dom ranking, certificate → testeables sin BD/LLM/red); **dependencias inyectables y perezosas** (LLM, GitHub App, repo); **LLM fuera del camino crítico**.

## 12. Modos de despliegue (una base, dos modos)

| | **Demo / SaaS-lite** | **Cliente regulado / air-gapped** |
|---|---|---|
| Frontend | Vercel | Servido desde infra del cliente |
| Supabase | Supabase cloud | **Supabase self-hosted** (ya en `docker-compose`) |
| LLM | Ollama local | Ollama local (sin internet) |
| GitHub | GitHub.com | GitHub Enterprise self-hosted |
| Firma | clave en backend | clave en HSM/infra del cliente |

El foso (datos + LLM + firma en infra del cliente) se mantiene en ambos. El modo air-gapped se documenta como argumento de viabilidad; no se empaqueta en este slice.

## 13. Testing (TDD, sin depender de Supabase/Ollama/GitHub — mocks)

- **`triage/signals` + `engine`:** tabla de casos por categoría (flaky por retry, flaky por historial mismo-SHA, mantenimiento por DOM+test-unchanged, defecto real por aserción novedosa, infra por co-fallo masivo, ambiguo → desempate).
- **`heal/dom`:** dado old/new DOM, el candidato robusto correcto gana el ranking; preferencia getByRole > testid > text > css.
- **`actions/*`:** con `CodeHost` mockeado, cada actuador produce el artefacto correcto en estado `proposed`; cuarentena **siempre** crea ticket de deuda.
- **`certify/signing`:** firmar→verificar OK; manipular el JSON → verify falla (tamper-evident).
- **`certify/certificate`:** desglose y veredicto correctos con triaje mockeado.
- **`learning/calibration`:** una corrección ajusta el umbral/etiqueta y el siguiente triaje la respeta.
- **`ci/github_webhook`:** HMAC válido pasa; inválido → 401.
- **Endpoints:** repo/auth/LLM/GitHub mockeados (patrón `tests/test_api_v2.py`).
- **RLS / aislamiento:** org A no ve triajes/acciones/certificados de org B.
- **Gate:** dado un run con defecto real novedoso → `failure`; todo curado/cuarentena → `success`.

## 14. Criterios de aceptación

- [ ] `POST /v2/ci/webhook` con artefacto del reporter crea run + triaja cada fallo + publica check run.
- [ ] Triaje clasifica correctamente los 4 tipos en la suite de casos (determinista, sin LLM).
- [ ] Un selector roto (DOM cambió, test sin cambios) → `SelfHealActuator` abre **PR borrador** con locator robusto.
- [ ] Un flaky conocido → cuarentena + **ticket de deuda** (nunca sin ticket); reconocido sin LLM.
- [ ] Un defecto real novedoso → ticket enriquecido con **linaje cross-proyecto** y, si existe, fix histórico.
- [ ] El gate **bloquea** con defecto real novedoso y pasa a **verde** tras aprobar el self-heal.
- [ ] Se genera un **Release Assurance Certificate** firmado; `verify` da OK y falla si se manipula.
- [ ] Una corrección humana ajusta `tenant_calibration` y cambia el siguiente triaje (lazo).
- [ ] Bandeja de aprobación Nivel 2 (Vercel) lista/aprueba/rechaza ítems en vivo (Realtime).
- [ ] Suite TDD verde sin Supabase/Ollama/GitHub (mocks).
- [ ] `docker-compose up` levanta el stack real (API + frontend + Ollama + Supabase self-hosted).

## 15. Mapeo a los pesos del concurso

| Criterio | Peso | Palanca |
|---|---|---|
| Innovación | 20% | Agéntico + self-healing + auto-evaluado + DNA federado privado + **motor determinista auditable** |
| Eficiencia | 20% | API 0€ + **ahorro de horas medible** + LLM solo en ambiguos/narrativa |
| Calidad MVP | 15% | Demo de 3 actos, e2e, innegable |
| Escalabilidad | 15% | Multitenant, conocimiento que se compone, Supabase escala |
| Impacto | 15% | Ataca la amenaza existencial de MTP; ROI cuantificable (% auto-triado, horas, PRs aceptados) |
| Capacidad | 10% | Amplitud de stack (agentes, self-heal, pgvector/RLS, GitHub App, firma Ed25519) |
| Viabilidad | 5% | Servicios → producto recurrente facturable |

## 16. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Self-heal general es difícil para un solo dev | Acotar al caso común de locator Playwright; repo de demo controlado; resto narrado |
| El "DOM cambió" necesita snapshots que hoy no existen | El `mnemo-playwright-reporter` los emite; controlamos el repo de demo |
| Alucinación del LLM rompe la certificación | Determinista-primero; LLM capado a 0.7 y marcado; firma sobre traza reproducible |
| Tensión nube (Vercel) vs. privacidad on-premise | Frontend = solo cliente; datos/LLM/firma en backend; modo self-hosted documentado |
| Scope creep (5 subsistemas) | Profundidad solo en triaje/acción/certificación; ① reusa ingesta, ⑤ es ligera |
| Honestidad técnica ante el jurado | No presentar lo narrado como construido; la demo e2e hace innecesario exagerar |

## 17. Guion de demo (jurado, ~3 min)

```
[0] Repo Playwright en verde. Dashboard (Vercel): org "MTP", proyecto sano, tendencia OK.
[Acto 1 — DEFECTO REAL]  push de bug real → test rojo → webhook → triaje "defecto real
   novedoso, riesgo alto" → GATE ROJO → Issue enriquecido (root-cause + linaje) → cert NO-APTO.
[Acto 2 — SELECTOR ROTO]  push que cambia la UI → locator not found → triaje "mantenimiento
   (DOM cambió, test sin cambios)" → PR BORRADOR cura a getByRole → aprobar → GATE VERDE →
   cert APTO-CON-RESERVAS.
[Acto 3 — FLAKY]  flaky conocido falla → reconocido al instante desde el DNA (sin LLM) →
   cuarentena + ticket de deuda → NO bloquea.
[Cierre]  Certificate firmado (PDF): veredicto, evidencia, sign-offs, RAGAS, firma Ed25519.
   "Esto entrega MTP por release." Corrijo un triaje → el agente se adapta en vivo (Realtime).
```

## 18. Datos de demo (seed)

- Repo Playwright/TS de demo con `mnemo-playwright-reporter` instalado y GitHub Actions configurado.
- Org "MTP" con 2-3 proyectos; Defect DNA sembrado con una familia compartida (p.ej. *timeout*) para que el **linaje cross-proyecto** y el fix histórico se vean reales en el Acto 1.
- Tres commits preparados (bug real / cambio de UI / flaky) para los tres actos.

## 19. Orden de implementación sugerido (fases del plan)

Dado el tamaño, la implementación se descompone en planes por orden de dependencias (cada uno con su TDD y verde antes de seguir):

| Fase | Entrega | Módulos / artefactos | Por qué primero |
|---|---|---|---|
| **F1 — Cimientos de ingesta** | Señales disponibles | `test_results`, `dom_snapshots`, `mnemo-playwright-reporter`, `POST /v2/ci/webhook` (HMAC) | Sin resultados por commit ni snapshots DOM no hay señales para el triaje |
| **F2 — El cerebro** | Triaje determinista | `triage/signals`, `triage/engine`, `triage/evidence`, `defect_families.label` | Núcleo de valor; funciones puras, testeable sin BD/LLM |
| **F3 — La acción** | Artefactos Nivel 2 | `actions/base`, `actions/self_heal` (+ `heal/dom`), `actions/quarantine`, `actions/ticket`, `ci/github_app` | El "wow"; depende del veredicto de F2 |
| **F4 — Certificación** | Gate + certificado | `certify/certificate`, `certify/signing`, `certify/render`, check run, `/v2/certificates*` | Cierra el lazo de aseguramiento; depende de F2/F3 |
| **F5 — Lazo + frontend** | Aprendizaje + bandeja | `learning/calibration`, `/v2/actions*`, `/v2/triage/correct`, bandeja de aprobación (Vercel) + Realtime | El foso; depende de que existan acciones que aprobar |
| **F6 — Demo + docs** | Demo e2e creíble | repo de demo, seed, `docker-compose`, `docs/functional` + `docs/technical` | Empaqueta el relato para el jurado |

Cada fase es un documento de plan independiente bajo `docs/superpowers/plans/`. F1-F4 son la espina dorsal mínima para la demo de 3 actos; F5 añade el foso; F6 lo hace presentable.
