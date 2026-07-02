# Mnemo — Análisis "al siguiente nivel" (2026-07-02)

**Base:** `feat/mnemo-ux-b-pulido` (últimos 10 commits = pulido UX/a11y) · **Método:** 5 lentes en paralelo (seguridad/multitenancy, arquitectura/escala, diferenciador central, frontend/UX/tests, producto/mercado), con verificación directa sobre el código de los hallazgos más graves. · **Pregunta del dueño:** *¿qué haría que una consultora IT de QA pague millones?*

---

## Veredicto en una frase

El camino a "millones" existe pero es estrecho y pasa **entero por una sola cosa**: convertir el **certificado de QA firmado y verificable** en la **unidad de facturación** de la consultora (facturar por *acta* auditable, no por horas). Todo lo demás (self-heal, flaky, onboarding, plan de pruebas) es *commodity* replicable — vitamina, no analgésico. **Y hoy ese único diferenciador está roto de tres formas independientes**, el producto que lo rodea está **muerto en runtime**, y hay un **agujero de seguridad cross-tenant** que te descalifica para tocar datos reales de clientes. No hace falta escribir más features de QA; hace falta arreglar y **afilar esa única cosa**.

---

## Los 3 "showstopper" (arreglar antes de CUALQUIER piloto o demo con datos reales)

### S1 · 🔴 Todo el pilar QA-Continuity está MUERTO en runtime (CI en verde lo esconde) — *verificado*
18 funciones de `frontend/src/lib/api/endpoints.ts` apuntan a rutas `/api/v2/*` que **no tienen su `route.ts`** proxy en Next. `next.config.ts` está vacío (sin rewrites), no hay `middleware.ts` ni catch-all `[...path]`. Resultado: la página carga (la UX pulida se ve) pero al pedir datos da **404**. Muertos: **Conocimiento, Onboarding, Knowledge Graph, Plan de pruebas** (los 4 items del bloque "Continuidad" del sidebar — el centro de la visión), más media integración Jira, root-cause, briefing de Autopilot y descarga de PDF del certificado. El backend **sí** implementa los 18. Ningún test ejerce la capa proxy → CI verde.
- **Rutas que faltan:** `graph`, `graph/gaps`, `knowledge`, `knowledge/ask`, `knowledge/search`, `knowledge/[id]`, `onboarding/domain-summary`, `onboarding/learning-path`, `test-plan/generate`, `test-plan/export/xray`, `automation/generate`, `automation/pr`, `integrations/jira`, `ingest/jira/pull`, `ingest/jira/file`, `defects/[id]/root-cause`, `runs/[id]/briefing`, `certificates/[run_id]/pdf`.
- **Fix:** un `route.ts` de ~10 líneas por endpoint (copiar `src/app/api/v2/orgs/route.ts`) + **un test de paridad** `endpoints.ts ↔ route.ts` que falle si falta alguno. Mecánico, ~1 día.

### S2 · 🔴 Confused-deputy cross-tenant en la GitHub App (N-C1) — *verificado*
`POST /v2/integrations/github` acepta `installation_id` como **input libre** (`api_v2.py:534-552`) sin verificar que esa instalación pertenezca al org. La app usa credenciales **globales** y `installation_token(installation_id)` acuña token para **cualquier** instalación (`ci/github_auth.py`, `ci/github_app.py`).
- **Escenario:** un owner/admin de un org cualquiera descubre el `installation_id` de la víctima (entero de baja entropía, visible en la URL de instalación) y hace `POST /v2/integrations/github {org_id:<suyo>, installation_id:<de la víctima>, repo_full_name:"victima/repo"}`. Luego `POST /v2/repo/index` **lee el código fuente completo** del repo de la víctima, o `POST /v2/automation/pr` **abre ramas/PRs** en su repo de producción.
- **Impacto:** lectura del código + inyección de PRs en el repo de OTRO cliente. Showstopper absoluto para vender a consultoras.
- **Fix:** no aceptar `installation_id` libre; vincularlo vía el *setup redirect* de la GitHub App y validar `GET /app/installations/{id}` → `account.login` coincide con el org; rechazar reconfiguraciones que cambien la cuenta.

### S3 · 🔴 El webhook `async` ejecuta trabajo bloqueante → congela el único event loop — *verificado (patrón)*
`ci_webhook` es `async def` (`api_v2.py:419`) pero llama **directamente** a `ingest_artifact`, `triage_run`, `generate` (cert) y `publish` (gate) — todo CPU (embeddings torch) + I/O bloqueante — sin `await`/`run_in_threadpool`. Con `Dockerfile:22` arrancando uvicorn **sin `--workers`** (1 loop), mientras un webhook procesa un run grande **todas** las peticiones de todos los tenants quedan congeladas (segundos a decenas). Un cliente tumba a todos.
- **Fix:** convertir `ci_webhook` a `def` (FastAPI lo manda al threadpool) o envolver cada paso en `run_in_threadpool`; arrancar con `--workers N`; y mover el post-procesado a cola (ver E1).

---

## El diferenciador (esto es lo que justifica los "millones") — roto de 3 formas

### D1 · 🔴 La verificación exige login → el acta NO es verificable por terceros *(sigue abierto desde 2026-06-27)*
`POST /v2/certificates/verify` lleva `Depends(get_current_user)` (`api_v2.py:868-873`), pese a que la verificación es criptografía pura (firma + payload + clave pública, ninguno secreto). No hay endpoint que publique `MNEMO_SIGNING_PUBLIC_KEY`. `render.py:70` promete "verificable con la clave pública" — promesa incumplida. **Un acta que solo el emisor puede verificar no es una atestación.** Es exactamente el auditor/regulador/cliente-del-cliente quien le daría valor, y es a quien se le niega.
- **Fix:** quitar el `Depends`, añadir `GET /v2/certificates/pubkey` (o `/.well-known/`), y publicar un verificador standalone.

### D2 · 🔴 No se puede certificar un release en VERDE — el caso central no produce acta — *verificado*
`service.generate` (`certify/service.py:26-27`) y `gate.publish` (`certify/gate.py:40-41`) lanzan `ValueError("run sin veredictos de triaje")` si no hay fallos. Los veredictos solo nacen de fallos → **un run donde todo pasa no genera certificado ni gate**. El gate solo dispara cuando *hubo* fallos. La promesa "este release pasó QA" **no emite acta** en el único caso que un cliente quiere firmar: el release limpio.
- **Fix:** permitir `generate`/`publish` con `verdicts=[]` → emitir acta `apto` de "run sin fallos". Es el caso más valioso comercialmente.

### D3 · 🟠 "La IA no firma" no es literal, y el invariante cuelga de UN booleano
El tiebreak LLM elige `category` (`triage/tiebreaker.py:53-62`) que **sí va firmada** en `breakdown`/`evidence[]` (`certificate.py:75-101`). Lo que el LLM no puede es fabricar un `apto` — pero **solo** porque `resolve_tiebreaks` fuerza `requires_approval=True` hardcodeado (`service.py:86`); `compute_verdict` **no mira `llm_assisted`** (`certificate.py:56-66`). El día que se añada "aprobar un tiebreak humano" (feature natural), un "flaky"/"infra" elegido por el LLM se vuelve `apto` firmado. El invariante no está protegido estructuralmente.
- **Fix:** en `compute_verdict`, tratar `llm_assisted`/`R6_ambiguous` como **nunca contribuyente a `apto`**, independientemente de `requires_approval`.
- *(Positivo: H1 — el LLM-judge contaminando el veredicto — está CERRADO; `ai_eval` se firma pero no lo leen ni `compute_verdict` ni `risk_score`.)*

### D4 · 🟠 El acta NO es byte-reproducible ni cross-language
Dos generaciones del mismo run dan certificados distintos por: (a) `created_at = now()` firmado (`api_v2.py:458`); (b) `ai_eval` no determinista del LLM, **firmado** dentro de `self_eval`; (c) **orden de `evidence` no total** (`get_triage_for_run` ordena por `created_at`, que empata en el insert transaccional → orden físico arbitrario). Además `canonical_json` es `json.dumps` de Python ad-hoc (no JCS/RFC 8785 ni DSSE) → un verificador en Go/JS puede producir bytes distintos para ciertos floats. Un tercero puede recomputar el **veredicto agregado** desde `evidence[]`, pero **no** re-derivar las categorías (las señales `evidence_bundle` no se firman).
- **Fix:** `ORDER BY tv.failure_id` para orden total; sacar `ai_eval` de lo firmado (envelope DSSE: firmar el `predicate` determinista, `ai_eval` como anotación); adoptar JCS/RFC 8785; incluir `evidence_bundle` firmado para reproducibilidad real del juicio.

### D5 · 🟠 El "foso" no compone (y puede ocultar defectos reales)
La calibración es un **lookup por PK con confianza fija 0.95**: `set_family_label` actualiza **una** familia (`defects/repository.py:830-870`), R0 (`triage/engine.py:23-27`) la devuelve con `confidence=0.95, requires_approval=False`, sin importar distancia semántica ni antigüedad. **No generaliza** a otras familias (existe `search_families_semantic` pero el motor no la usa). La métrica de "precisión" está sesgada por selección (solo familias etiquetadas), es circular (re-etiquetar infla) y solo modula la *confianza* del cert, no la clasificación. **Hueco de gate (P1):** si una familia etiquetada "flaky" recibe un fallo de aserción recurrente (no-novel) por colisión de fingerprint, R0 lo marca "flaky" 0.95 sin aprobación → contribuye a `apto` → **cloakea un defecto real**.
- **Fix:** que el label module el motor (no solo la confianza) y se mida precisión motor-puro; degradar la 0.95 fija por similitud/antigüedad; extender el guard R0 para no aplicar el prior ante `assertion_failure` recurrente.

### D6 · 🟠 Certificados duplicados + sin `key_id`/algoritmo → rotación imposible
Sin unique en `certificates.run_id` (`014_certificates.sql`); `save_certificate` siempre inserta (append-only) → varios certs por run, `get_certificate` devuelve el último → "el" certificado no está definido. El schema `mnemo.cert.v2` no lleva `key_id` ni `algorithm` → rotar la clave invalida **todos** los certs pasados. Y `verify` traga toda excepción → si `MNEMO_SIGNING_PUBLIC_KEY` está mal, **toda verificación devuelve `False` sin error** (sin validación del par de claves al arranque).
- **Fix:** unique/upsert por `run_id`; añadir `key_id`+`algorithm` al acta; validar el par de claves al construir el servicio y fallar ruidoso.

---

## Aislamiento y authz (bloquea vender a clientes regulados)

- **A1 · 🟠 Envenenamiento de calibración** *(sigue abierto)*: `set_family_label` solo exige **membership**, no owner/admin (`api_v2.py:638-654` → `repository.py:830-870`), a diferencia de integraciones y acciones. Un contratista junior etiqueta masivamente con etiquetas falsas → corrompe el "foso" y sesga el self-eval del certificado de todos los runs del org. **Fix:** exigir `role in ('owner','admin')`. Revisar también `update_triage_verdict`/`resolve_triage_run`.
- **A2 · 🟠 Webhook: secreto global único + sin anti-replay**: HMAC correcto (fail-closed, `compare_digest`, cap de tamaño) pero sin timestamp/nonce → un POST válido capturado se reenvía indefinidamente; con `run_uid=None` (es `Optional`) cada replay crea run nuevo y re-emite cert/gate. El secreto es **global** (no por-org): quien lo tenga POSTea artefactos controlados y Mnemo emite un cert "verde" automático. El certificado atestigua "alguien con el secreto envió esto", no que las pruebas se ejecutaran. **Fix:** timestamp firmado + ventana 5 min + nonce; `run_uid` obligatorio; secreto **por-org**; forzar `CI_SERVICE_ORG_ID`.
- **A3 · 🟡 `viewer`/`member` puede escribir en el repo del cliente**: `automation_pr` y `repo_index` (`api_v2.py:1217-1288`) solo exigen membership → cualquier miembro abre PRs draft y lee todo el árbol del repo. Mitigado (filename regex `*.spec.ts`, PR draft). **Fix:** exigir owner/admin.
- **A4 · 🟡 SSRF**: DNS-rebinding/TOCTOU en Jira (`jira/safe_url.py:15-23` valida la IP y la descarta, re-resolviendo en la petición real); Xray Server/DC **sin validación alguna** (`xray/config.py`); `XrayConfig.get_raw()` descifra credenciales **sin check de membership**. Latentes hoy (Xray no tiene endpoint de config alcanzable; Jira usa la `base_url` almacenada), pero frágiles. **Fix:** resolver-y-pinnear la IP; centralizar `validate_base_url` en el cliente; gatear `get_raw` por membership.
- *(Positivo verificado: **RLS intacta** — 19 tablas `public` con enable+force+policy `is_org_member`; hueco histórico de `org_integrations` cerrado en migración 013. Secretos sin hardcode ni logging. SQL parametrizado. JWT RS256/ES256 vía JWKS sin confusión de algoritmo — PR #56 correcto. ReDoS con cobertura real.)*

---

## Escala y operación (bloquea "cientos de clientes")

- **E1 · Pipeline post-ingesta síncrono sin cola ni reintento** (`api_v2.py:437-470`): triaje→cert→gate corren tras el commit, cada uno degradando en silencio; un fallo parcial deja runs "a medias" invisibles, sin backfill. **Fix:** cola idempotente (RQ/Arq/pgmq) + `202` tras el commit de ingesta.
- **E2 · N+1 de LLM en `/graph/gaps`** (`graph/gaps.py:220-270`): una llamada LLM por fila de gap, secuencial (20 gaps ≈ 20-40 s, roza `maxDuration=60`). Además N+1 de embeddings en la ingesta (`ci/ingestion_service.py:26-32`) y en `resolve_tiebreaks` (una conexión+commit+LLM por veredicto). **Fix:** batch.
- **E3 · Sin migraciones versionadas en prod**: `render.yaml` no tiene paso de migración; los `.sql` se aplican a mano; el runner on-prem re-ejecuta todo cada arranque sin tabla de versiones ni rollback. **Fix:** Alembic + paso de deploy.
- **E4 · Observabilidad cero + `/health` falsamente sano**: sin otel/prometheus/sentry, **ningún `logging.dictConfig`** → los `logger.exception` del webhook probablemente **ni se emiten**; `/health` devuelve estático sin tocar la BD (Render sigue verde con Postgres caído). **Fix:** logging JSON, Sentry, `/health` con `SELECT 1`.
- **E5 · Sin rate limiting** en ninguna ruta (incumple la propia norma del proyecto) → amplificación de coste/DoS en los endpoints LLM. **E6 · Embedder cargado 5+ veces** en memoria (riesgo OOM en Render de ~1 GB) — un solo `LocalEmbedder` singleton. **E7 · Doble cold-start** apilado (Vercel + Render free). **E8 · God-objects**: `api_v2.py` (1297 líneas), `defects/repository.py` (986). **E9 · DRY**: `_connect`/`_set_claims` duplicados 8×; `_set_claims` es **scaffolding muerto** (el pooler bypassa RLS) = 2 round-trips SQL desperdiciados por escritura.

---

## Producto y adopción diaria

- Sin **listar/elegir runs** (hay que pegar el UUID — `RunSelector.tsx:59`); no existe `GET /v2/runs`. Sin **bandeja global de acciones** ni **historial**. Sin **gestión de miembros/roles** con efecto en la UI (backend sin endpoint). Onboarding es fino (3 mutaciones Q&A, no flujo guiado). Idioma **EN/ES mezclado** (login/signup/org en inglés, el resto en español). Mensajes de error crudos al usuario (`"Request failed with status 404"`).
- **Ausente para enterprise:** SSO/SAML/SCIM, **audit log inmutable** (irónico para un producto de compliance), billing/metering/entitlements, on-prem real (la auth depende de Supabase cloud → air-gap imposible hoy), DPA/pentest/SOC2.
- **Higiene:** archivos duplicados sin trackear `src/repo_ingest/{repository,service} 2.py` (¡difieren del original!), `tests/test_security_jwks 2.py`, y directorios `.../[x] 2/` (basura de iCloud/Finder) — limpiar antes de mergear.

---

## Negocio: ¿quién paga millones y por qué?

- **El usuario ≠ el comprador.** Los QA que usan onboarding/plan son *champions*, no firman millones. El comprador económico es el **socio/Head of Delivery** (dueño del P&L) o, derivado, el **CISO/Head of Quality del cliente final regulado** que **exige** la evidencia de auditoría y tiene el presupuesto de compliance.
- **El dolor de millones** no es "onboardear más rápido" (vitamina). Es la **compresión de margen** (facturan por horas/cuerpos) y la **incapacidad de diferenciarse/retener cuentas reguladas**. El certificado abre facturar por **RESULTADO/acta** en vez de por horas → convierte a Mnemo de *proveedor de herramienta* (coste) en *socio de margen* (ingreso). Ese es el cambio de modelo, y es lo único que llega a "millones".
- **Aritmética creíble:** modelo **por-cliente/por-acta** (€2-5k/cliente/año → consultora de 20-40 clientes = €40-200k ACV → ~50 consultoras ≈ €4M ARR). **No** cierra como "vender otra herramienta de self-heal" (techo €500-2k/mes, se pierde contra mabl/Datadog).
- **Riesgos que matan el negocio:** (1) **IP base 11** del concurso MTP — podría ceder la explotación del único activo defendible; leer la base literal **antes** de cualquier pitch. (2) **Replicabilidad**: todo el stack es de estantería (Ed25519 stdlib) — mabl/Tricentis añaden "acta firmada" en un trimestre si ganas tracción; el foso real es *ser el estándar adoptado + corpus por cliente + distribución*. (3) El disclaimer se **autoneutraliza** ("no es garantía ni certificación legal", `certificate.py:5-9`) → ningún auditor lo paga por obligación salvo que se mapee a un marco (SOC2/ISO 25010/gobierno de release).

---

## Plan priorizado (utilidad × esfuerzo)

**GATE 0 (existencial, barato):** resolver la **IP de la base 11** y elegir **un** modelo (on-prem-consultoras vs SaaS). Bloquea todo lo demás; es riesgo-evitación, no upside.

**Sprint 1 — "Que funcione y no filtre" (showstoppers):**
1. S1 — 18 `route.ts` + test de paridad (~1 día). *El pilar del producto está muerto sin esto.*
2. S2 — binding org↔instalación GitHub (cerrar N-C1).
3. S3 — sacar el webhook del event loop + `--workers`.
4. Limpieza de archivos ` 2` / directorios basura.

**Sprint 2 — "Convertir el certificado en EL producto" (lo que vale millones):**
5. D1 — `/verify` público + publicar la clave + verificador standalone.
6. D2 — certificar releases en verde.
7. D3+D4 — invariante "IA nunca favorece" estructural + acta byte-reproducible (orden total, `ai_eval` fuera de la firma, JCS).
8. Reposicionar: "el estándar de acta firmada de QA — SLSA para QA"; mapear el acta a un marco de compliance; reformular el disclaimer.

**Sprint 3 — "Vendible a regulados" (envoltorio + aislamiento):**
9. A1/A2/A3 — authz de etiquetado owner/admin, anti-replay + secreto por-org, owner/admin en escritura de repo.
10. Cola async (E1), observabilidad + `/health` real (E4), rate limiting (E5), migraciones versionadas (E3).
11. Listar/elegir runs + bandeja global + gestión de miembros/roles (adopción diaria).

**Sprint 4 — "Que componga y escale el ingreso":**
12. D5 — que la corrección retroalimente el motor (foso real) + métrica motor-puro.
13. Workspaces por cliente + panel de cartera + white-label + metering (facturación por-acta) + SSO/audit-log (enterprise).

### La respuesta directa
Una consultora **no** paga millones por "otro autopilot de QA". Paga millones por poder **facturar a sus clientes un acta de calidad firmada y verificable por auditores** — por cambiarles el modelo de horas a resultado, con Mnemo como la infraestructura que emite y verifica esas actas y guarda la memoria por cliente. Hoy ese acta está **detrás de un login, no se emite para el caso verde, no es reproducible, y el producto que la rodea da 404** — más un agujero cross-tenant que impide tocar datos reales. La probabilidad de "millones" no depende de más features; depende de **(0) blindar la IP, (1) abrir/estandarizar el acta, (2) facturarla por cliente**.
