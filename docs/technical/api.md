# Mnemo — Referencia de API (`/v2`)

Referencia de todas las rutas que monta el backend. Fuente de verdad: `src/api_v2.py` (único router, incluido por `asgi.py`) y los modelos de `src/multitenant_models.py`.

El entrypoint de producción es `asgi:app` (`uvicorn asgi:app`). Monta **solo** el router `/v2`; el RAG v1 legacy (`api.py`) no forma parte del arranque.

---

## Autenticación

| Esquema | Cómo | Dónde |
|---|---|---|
| **JWT** | `Authorization: Bearer <jwt-supabase>` (validado contra el JWKS de Supabase) | Todas las rutas salvo las de abajo |
| **Pública** | Sin credenciales | `GET /v2/health`, `GET /v2/certificates/pubkey`, `POST /v2/certificates/verify` |
| **HMAC** | Firma `X-Hub-Signature-256` del cuerpo con `CI_WEBHOOK_SECRET` | `POST /v2/ci/webhook` |
| **Token de ingesta** | `Authorization: Bearer mnemo_it_…` o cabecera `X-Mnemo-Token` | `POST /v2/ci/ingest` |

En la columna *Auth* de las tablas: **miembro** = el usuario debe pertenecer a la org (la comprobación la hace el repositorio; según el endpoint, un no-miembro recibe 403, 404 o una lista vacía); **owner/admin** = además exige ese rol en la org.

## Errores comunes

| Código | Cuándo |
|---|---|
| 400 | Datos inválidos detectados en el servicio (`ValueError`) |
| 401 | Sin token, token inválido/caducado, firma HMAC incorrecta o token de ingesta inválido/revocado |
| 403 | No es miembro, o falta el rol owner/admin |
| 404 | Recurso inexistente o ajeno (run, familia, certificado, ítem, proyecto…) |
| 409 | Conflicto (instalación de GitHub ya vinculada a otra org; import sin integración Atlassian) |
| 413 | Subida o cuerpo por encima de la cota (`INGEST_MAX_BYTES` / `CI_MAX_BODY_BYTES`, 10 MiB por defecto) |
| 422 | Validación del cuerpo (Pydantic) o regla de negocio concreta (ver cada endpoint) |
| 429 | Cuota de import excedida |
| 500 | Fallo al renderizar el PDF del acta |
| 502 | Error de base de datos (`Database error`) o de una API externa (GitHub, Jira, Xray) |
| 503 | Stack multitenant sin configurar (`Multi-tenant KB not configured`), clave de firma ausente, integración externa sin configurar o IA no disponible donde no hay degradación posible |

## Degradación sin LLM

El LLM es opcional en casi toda la API. Si el proveedor no se puede construir o falla, los endpoints devuelven un resultado determinista en lugar de un 500:

- **Sin IA (degradan a determinista):** narrativa de assurance (`narrative: null`), briefing, `defects/ask`, `knowledge/ask`, onboarding, plan de pruebas, `automation/generate`, recomendaciones de `graph/gaps`, ticket y self-heal de acciones.
- **Requieren IA (503 si no hay):** `POST /v2/defects/{id}/root-cause` y `POST /v2/knowledge/proposals/{id}/refine` (la propuesta queda intacta).
- **Nunca usan IA:** el veredicto firmado del acta, el índice de continuidad y el acta de traspaso, el import desde Atlassian.

---

## Salud

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/health` | `{status, model, llm, multi_tenant_enabled}`. Con `?probe=true` hace una llamada mínima real al LLM e informa del error crudo; sin `probe` solo valida la configuración | Pública |

---

## Organizaciones

| Método | Ruta | Cuerpo | Respuesta | Auth |
|---|---|---|---|---|
| `GET` | `/v2/orgs` | — | `OrganizationResponse[]` | JWT |
| `POST` | `/v2/orgs` | `{name}` (2–120) | `OrganizationResponse`; el creador queda como `owner` | JWT |
| `POST` | `/v2/orgs/join` | `{join_code}` (4–32) | `OrganizationResponse`; 404 si el código no existe | JWT |

`OrganizationResponse = {id, name, join_code, role, created_at}`.

---

## Ingesta y CI

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/ingest/report` | Multipart: `file`, `project`, `org_id`, `source` (por defecto `auto`). → `IngestReportResponse {run_id, ingested, known, novel, deduplicated}`. Solo ingesta (no encadena triaje ni acta) | JWT + miembro |
| `POST` | `/v2/ingest/jira/file` | Multipart: `file` (export de Jira), `project`, `org_id` → `JiraIngestResponse {run_id, ingested, known, novel, skipped}` | JWT + miembro |
| `POST` | `/v2/ingest/jira/pull` | `{org_id, project}`: pull vía la integración Jira configurada → `JiraIngestResponse`; 502 si falla la API de Jira | JWT + miembro |
| `GET` | `/v2/runs?org_id=&project=&limit=&offset=` | Histórico de runs (más reciente primero) con el veredicto del acta más reciente, `risk_score` y nº de fallos. `limit` por defecto 50, acotado a 1–100; lista vacía si no es miembro | JWT + miembro |
| `POST` | `/v2/ci/webhook` | Artefacto JSON de CI firmado (ver abajo) → `CiWebhookResponse` | HMAC |
| `POST` | `/v2/ci/ingest` | Ingesta genérica: multipart `file` + `project` (+ `source`, por defecto `auto`) | Token de ingesta |
| `POST` | `/v2/ingest/tokens` | `{org_id, name}` → crea un token. El token en claro **solo se devuelve aquí**; en BD vive su sha256 | JWT + owner/admin |
| `GET` | `/v2/ingest/tokens?org_id=` | Lista los tokens de la org (sin el claro) | JWT + miembro |
| `POST` | `/v2/ingest/tokens/{token_id}/revoke` | Revoca un token → `{revoked: true}`; 403 si no existe, ya estaba revocado o falta el rol | JWT + owner/admin |

Las rutas de subida aplican `INGEST_MAX_BYTES` (413). La ingesta de reports es idempotente: reentregar el mismo artefacto devuelve `deduplicated: true` sin repetir el pipeline.

### `POST /v2/ci/webhook`

Cuerpo `CiRunArtifact`: `{project, org_id, commit_sha, source (por defecto "playwright"), run_uid?, tests: [{test_name, status: pass|fail|flaky|skipped, retried, error_type?, message?, trace?, file?, line?, dom?}]}` (máx. 10 000 tests).

Orden de comprobaciones: cota `CI_MAX_BODY_BYTES` (413) → firma HMAC (401) → `CI_SERVICE_USER_ID` configurado (503) → validación del artefacto (422) → si `CI_SERVICE_ORG_ID` está definido, rechaza artefactos de otra org (403). La ingesta es idempotente por `(org_id, run_uid)`.

Respuesta `CiWebhookResponse = {run_id, ingested, known, novel, results_recorded, snapshots_saved, deduplicated, triage, verdict, gate}`.

### `POST /v2/ci/ingest`

Cualquier CI se enchufa **con un token, sin instalar nada propietario**: se sube el report tal cual lo genera el runner (JUnit, TestNG, Robot, Allure, Playwright, Cypress o Cucumber, con autodetección).

Orden: autenticación por token (401) → cota por `Content-Length` (413) → parseo del multipart (422 si faltan `file` o `project`; 400 si `project` supera 200 caracteres). El multipart se parsea a mano **después** de autenticar, para que un anónimo no pueda forzar el volcado de archivos enormes.

```bash
curl -sS -H "Authorization: Bearer $MNEMO_INGEST_TOKEN" \
     -F file=@test-results/junit.xml \
     -F project=mi-proyecto \
     https://<backend>/v2/ci/ingest
# → {"run_id": "…", "ingested": …, "known": …, "novel": …, "deduplicated": false,
#    "triage": {...}, "verdict": "apto|apto-con-reservas|no-apto|sin_confirmar", "gate": "…"}
```

El token actúa con la identidad de quien lo creó (owner/admin): los membership-checks del pipeline aplican tal cual, y si esa persona deja la organización sus tokens dejan de funcionar. **Nota operativa:** degradar a alguien de owner/admin a member NO revoca sus tokens existentes; si se le retira la confianza, hay que revocarlos explícitamente. Tabla `ingest_tokens` (migración `024`): RLS con lectura para miembros y escritura solo admin, sin grants de escritura a `authenticated`; la gestión va siempre por la API.

### Pipeline post-ingesta (webhook y `/ci/ingest`)

Si el run no está deduplicado, ambos endpoints encadenan **ingesta → triaje → acta firmada → gate**, cada etapa best-effort: si una falla queda en el log, su campo de la respuesta vuelve `null` y lo ya commiteado se conserva.

Después de enviar la respuesta, una `BackgroundTask` genera **propuestas de conocimiento** para hasta 3 familias sin lección (el CI no espera al LLM). Se omite si el stack multitenant o el LLM no están configurados; los fallos solo se registran en el log.

---

## Triaje

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/triage/run/{run_id}` | Veredictos de triaje del run → `TriageVerdictResponse[] {id, failure_id, category, confidence, rule_applied, requires_approval, llm_assisted, status, evidence_bundle}` | JWT + miembro |
| `POST` | `/v2/triage/run/{run_id}/resolve` | Resuelve los tiebreaks pendientes del run → `{resolved, pending}` | JWT + miembro |

---

## Assurance y briefing

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/assurance/run/{run_id}` | `{run_id, ingested, known, novel, risk, top_families[], narrative}`. `risk = "atencion"` si hay familias nuevas; si no, `"ok"`. `narrative` es `null` sin LLM. 404 si el run no existe | JWT + miembro |
| `GET` | `/v2/runs/{run_id}/briefing` | Resumen ejecutivo: `{verdict, summary, recommendation, highlights[], citations[]}`. `verdict` vale `"sin certificar"` si el run no tiene acta. Degrada sin LLM. 404 si el run no existe | JWT + miembro |

---

## Defectos y calibración

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/defects?org_id=` | Familias de defecto → `{id, title, status, occurrence_count, first_seen, last_seen, label, has_lesson, projects[]}[]` | JWT + miembro |
| `GET` | `/v2/defects/{defect_id}` | Linaje: `{family: {id, title, status, occurrence_count, root_cause, label_reason}, failures: [{id, test_name, error_type, project, source, created_at}]}` | JWT + miembro |
| `PATCH` | `/v2/defects/{family_id}/label` | `{label, reason?}` → `{family_id, label}`. Ver nota | JWT + miembro |
| `POST` | `/v2/defects/{defect_id}/root-cause` | Causa raíz por LLM → `{defect_id, root_cause, cached}`. Devuelve la cacheada salvo `?regenerate=true`. 404 si no existe; 503 si la IA no está disponible o no produce resultado | JWT + miembro |
| `POST` | `/v2/defects/ask` | `{org_id, question}` (≤2000) → `{answer, citations[], families[]}`: búsqueda semántica sobre las familias (k=8) + respuesta del LLM; degrada sin LLM | JWT + miembro |
| `GET` | `/v2/calibration/metrics?org_id=` | Métricas del lazo de aprendizaje → `{total, aciertos, accuracy, familias_calibradas, por_categoria}`; 404 si la org no existe o no es miembro | JWT + miembro |

**Etiquetado.** `label` ∈ `flaky` / `real` / `maintenance` / `infra` / `unknown` (otro valor → 422; familia inexistente o ajena → 404). El cambio se registra como corrección humana frente a la predicción del motor, que alimenta la calibración. Si llega `reason`, el endpoint **embebe la razón** (best-effort: si el modelo falla, la etiqueta se guarda igual con el vector a `NULL` y `scripts/reembed.py` lo completa después). La búsqueda semántica de familias tiene en cuenta ese vector, y la razón vuelve como `label_reason` en el linaje.

**Root cause → propuesta.** Cuando se calcula una causa raíz nueva, se deja además una propuesta de lección en la bandeja de conocimiento (best-effort; nunca rompe la respuesta).

---

## Acciones (self-heal)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/actions/run/{run_id}/propose` | Propone acciones sobre los veredictos del run → `{quarantine, ticket, self_heal, skipped}` | JWT + miembro |
| `GET` | `/v2/actions?org_id=&status=` | Acciones de la org; `status` opcional ∈ `proposed` / `approved` / `rejected` / `materializing` / `materialized` (otro valor → 400) | JWT + miembro |
| `POST` | `/v2/actions/{action_id}/approve` | Aprueba y materializa (p. ej. quarantine → PR en GitHub) → `{approved, materialized, artifact_ref}`. 400 datos inválidos, 503 GitHub App sin configurar, 502 error de la API de GitHub | JWT + miembro |
| `POST` | `/v2/actions/{action_id}/reject` | `{reason}` → `{rejected}` | JWT + miembro |

Por categoría del triaje: `flaky` → cuarentena, `real` → ticket con causa raíz, `maintenance` → self-heal. Las partes con LLM (causa raíz del ticket, explicación del self-heal) se construyen en el momento de uso y degradan si el LLM no está.

---

## Certificados (actas) y verificación pública

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/certificates/run/{run_id}` | Emite el acta firmada del run → `CertificateResponse`. 422 si el run no existe o tiene fallos sin triar; 503 sin clave de firma | JWT + **owner/admin** |
| `GET` | `/v2/certificates/{run_id}` | Lee el acta → `CertificateResponse`; 404 si no existe | JWT + miembro |
| `GET` | `/v2/certificates/{run_id}/html` | Acta renderizada en HTML; 404 si no existe | JWT + miembro |
| `GET` | `/v2/certificates/{run_id}/pdf` | Descarga en PDF (`certificate-{run_id}.pdf`); 404 si no existe, 500 si falla el render | JWT + miembro |
| `GET` | `/v2/certificates/pubkey` | `{algorithm: "ed25519", public_key_pem}`; 503 si no hay clave pública configurada | **Pública** |
| `POST` | `/v2/certificates/verify` | `{canonical_json, signature}` → `{valido}` | **Pública** |
| `POST` | `/v2/gate/run/{run_id}` | Publica el resultado del gate como check en el commit de GitHub → `{verdict, conclusion, check_run_url}`. 422 datos inválidos, 503 GitHub App sin configurar, 502 error de GitHub | JWT + miembro |

`CertificateResponse = {run_id, verdict, risk_score, canonical_json, signature, created_at, share}`. `share` es el acta empaquetada (base64url) para viajar en el fragmento de un enlace de verificación; cadena vacía si no cabe en un enlace usable.

`verdict` ∈ `apto` / `apto-con-reservas` / `no-apto` / `sin_confirmar`. El acta es **schema `mnemo.cert.v3`** e incluye un **`execution_manifest`** firmado (`{total, passed, failed, skipped, flaky, complete, source_format, artifact_sha256, commit_sha}`): registra qué se ejecutó, no solo los fallos. Un run limpio sin manifiesto completo (no se puede probar que corrieron tests) da **`sin_confirmar`**, no `apto`; un run con fallos sigue siendo rojo. Emitir a mano exige owner/admin; la auto-emisión del pipeline de CI no.

Conclusión del gate: `no-apto` → `failure`, `apto-con-reservas` y `sin_confirmar` → `neutral`, `apto` → `success`.

`pubkey` y `verify` son **sin auth a propósito**: la verificación es criptografía pura (firma + payload + clave pública, sin datos de ningún tenant) y su valor está en que un tercero (cliente, auditor) pueda comprobar un acta sin cuenta en Mnemo, también desde la página `/verify` del frontend u offline con la clave pública. `verify` es agnóstico del schema: sirve igual para actas de release y de traspaso. Como depende del servicio de certificados, devuelve 503 si el stack multitenant no está configurado.

---

## Continuidad y acta de traspaso

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/continuity?org_id=` | Sin `project`: `{projects: [...]}`, los proyectos con runs o conocimiento (lista vacía si no es miembro) | JWT + miembro |
| `GET` | `/v2/continuity?org_id=&project=` | Índice de continuidad del proyecto → `{score, dimensions[], inventario}`. 404 si el proyecto no existe o el usuario no es miembro (mismo 404 en ambos casos, para no revelar qué orgs existen) | JWT + miembro |
| `POST` | `/v2/continuity/handover` | `{org_id, project}` (1–200) → emite y firma el acta de traspaso: `{canonical_json, signature, share, score, created_at}`. 403 sin rol, 404 proyecto inexistente, 503 sin clave de firma | JWT + **owner/admin** |
| `GET` | `/v2/continuity/handover/latest?org_id=&project=` | Última acta del proyecto con su enlace regenerado → `{canonical_json, signature, score, project, created_at, share}`; 404 si no hay ninguna o no es miembro | JWT + miembro |

**Índice.** Determinista y 100 % SQL (sin LLM): misma entrada, mismo número. Cuatro dimensiones, cada una `{key, label, num, den, ratio, weight}`:

| `key` | Mide | Peso |
|---|---|---|
| `memoria_defectos` | Familias recurrentes (≥2 apariciones) con conocimiento activo vinculado | 0,35 |
| `razon_etiquetas` | Familias etiquetadas por un humano cuya corrección tiene razón escrita | 0,25 |
| `oficio` | Cuántos de los kinds `runbook`, `dato_prueba`, `contacto`, `decision` tienen al menos un ítem | 0,25 |
| `reglas_respaldadas` | Reglas de negocio y riesgos con una lección o patrón del mismo dominio | 0,15 |

`score` es la media ponderada (0–100) sobre las dimensiones con denominador; si ninguna lo tiene vale `null` («sin datos suficientes»). `inventario` = `{familias, familias_con_leccion, conocimiento_por_kind, dominios, etiquetas, etiquetas_con_razon}`.

**Acta de traspaso.** Schema `mnemo.traspaso.v1`; el payload firmado lleva `{schema, org_id, project, created_at, emitted_by, continuity: {score, dimensions}, inventario, mnemo_version, key_id}`. El desglose y los pesos viajan dentro, así que el acta es recalculable y comparable con otras emitidas con pesos distintos. Se verifica por la misma puerta pública que el acta de release.

---

## Conocimiento (memoria QA)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/knowledge` | Crea un ítem: `{org_id, kind, title, challenge?, approach?, outcome?, domain?, tags[], project?, defect_family_id?, run_id?}`. 400 si el kind no es válido; 403 si no es miembro | JWT + miembro |
| `GET` | `/v2/knowledge?org_id=&kind=&domain=&project=&status=&defect_family_id=` | Lista ítems (filtros opcionales) | JWT + miembro |
| `GET` | `/v2/knowledge/{item_id}?org_id=` | Un ítem; `org_id` es obligatorio (422 si falta); 404 si no existe | JWT + miembro |
| `PATCH` | `/v2/knowledge/{item_id}` | `{org_id, …campos}`: edita `kind`, `title`, `challenge`, `approach`, `outcome`, `domain`, `tags`, `project` o `status` (`activo` / `obsoleto`). 404 si no existe o sin permiso | JWT + autor, u owner/admin |
| `DELETE` | `/v2/knowledge/{item_id}?org_id=` | Borrado duro → `{deleted: true}`; misma autoridad que la edición | JWT + autor, u owner/admin |
| `POST` | `/v2/knowledge/search` | `{org_id, query, k}` (k 1–100, por defecto 8): búsqueda semántica unificada sobre ítems y familias de defecto → `[{id, type: knowledge|defect, title, content, confidence}]` | JWT + miembro |
| `POST` | `/v2/knowledge/ask` | `{org_id, question}`: respuesta en lenguaje natural citando las fuentes; degrada sin LLM | JWT + miembro |

`kind` ∈ `regla_negocio`, `flujo`, `riesgo`, `glosario`, `leccion`, `reto`, `patron`, `runbook`, `dato_prueba`, `contacto`, `decision`. El contenido de las familias en la búsqueda incluye la razón de la etiqueta humana.

### Propuestas («la IA propone, el humano aprueba»)

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/knowledge/proposals?org_id=&status=` | Bandeja de propuestas (`status` por defecto `pending`) | JWT + miembro |
| `POST` | `/v2/knowledge/proposals/generate` | `{org_id, family_ids?, cap}` (cap 1–20, por defecto 5): genera propuestas desde familias sin lección, una llamada LLM por familia → `{created, failed, remaining}` | JWT + miembro |
| `POST` | `/v2/knowledge/proposals/{id}/approve` | `{kind (por defecto leccion), title, challenge?, approach?, domain?, outcome?, tags[]}`: aprueba e inserta en la memoria de forma atómica. 403 si falta el rol o ya no está pendiente | JWT + owner/admin |
| `POST` | `/v2/knowledge/proposals/{id}/reject` | `{reason}` (≤500) → `{rejected: true}`; 403 si falta el rol o ya no está pendiente (una propuesta resuelta no se reabre) | JWT + owner/admin |
| `POST` | `/v2/knowledge/proposals/{id}/refine` | Una llamada LLM que condensa la propuesta y sugiere `kind`/`domain`. 404 si no existe o ya está resuelta; 503 si el LLM cae (la propuesta queda como estaba) | JWT + miembro |
| `POST` | `/v2/knowledge/import` | `{org_id, refs[]}` (1–10, cada una ≤500) → `{created[], refreshed[], skipped[], errors[{ref, reason}]}` | JWT + miembro |

Además de `generate`, las propuestas nacen automáticamente al calcular una causa raíz y tras cada ingesta de CI (ver *Pipeline post-ingesta*).

**Import.** Determinista y sin LLM (el refinado es por propuesta). Acepta claves de Jira (`PAY-123`) y URLs de páginas de Confluence **del site configurado**; el host de una URL pegada nunca se usa para pedir datos. Deja las propuestas en la bandeja con enlace al original; los errores van por referencia en la respuesta. 409 sin integración Atlassian, 429 al superar 60 importaciones (secciones) por hora y org, 502 si falla la API de Jira.

---

## Onboarding

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/onboarding/domain-summary` | `{org_id, topic}` → `{rules, systems, existing_tests, historical_bugs, risks, citations}` sobre la memoria del proyecto. Sin LLM: listas vacías y las fuentes encontradas como citas | JWT + miembro |
| `POST` | `/v2/onboarding/learning-path` | `{org_id, topic}` → `{days: [{day, items}], citations}`. Sin LLM: un día con aviso y las fuentes como citas | JWT + miembro |

---

## Plan de pruebas y Xray

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/test-plan/generate` | Multipart: `org_id`, `case_format` (por defecto `manual`) y la historia de usuario con prioridad `hu_text` > `jira_url` > `file`. → `{plan, citations}`. 400 si no hay HU o está vacía; 403 si no es miembro. Sin LLM devuelve un plan de respaldo con las fuentes | JWT + miembro |
| `POST` | `/v2/test-plan/export/xray` | `{org_id, plan, case_format, project_key}` → `{keys}`. 403 si no es miembro, 503 si Xray no está configurado, 502 si falla el import | JWT + miembro |

La integración Xray vive en `org_integrations` con `provider='xray'` (migración `019`). No tiene endpoints de configuración propios: solo se usa desde el export.

---

## Automatización e indexación del repo

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/automation/generate` | `{case, org_id, style_sample?}` → `{code, filename, notes}`: test Playwright (`.spec.ts`). 400 si `case` está vacío. Sin LLM devuelve una plantilla con `test.fixme()` a completar | JWT (sin check duro de org) |
| `POST` | `/v2/automation/pr` | `{org_id, code, filename (*.spec.ts), title?}` → `{pr_url}`: abre un draft PR que añade `tests/{filename}`. 403 si no es miembro, 503 GitHub sin configurar, 502 error de GitHub | JWT + miembro |
| `POST` | `/v2/repo/index` | `{org_id}`: indexa los tests del repo GitHub de la org como assets. 403 si no es miembro, 503 GitHub sin configurar, 502 error de GitHub | JWT + miembro |
| `GET` | `/v2/repo/tests?org_id=` | Assets de test indexados de la org | JWT + miembro |

Estilo de `automation/generate`, en cascada: `style_sample` manual → tests reales del repo (few-shot) → convenciones estándar. El retrieval del few-shot es membership-gated: un no-miembro no recibe 403, pero obtiene el test sin ejemplos del repo.

---

## Grafo y huecos

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `GET` | `/v2/graph?org_id=&focus=&limit=` | Grafo de conocimiento (nodos: dominios, familias, ítems; aristas: relaciones). `limit` por defecto 200, acotado a 500 en servidor | JWT + miembro |
| `GET` | `/v2/graph/gaps?org_id=&recommendations=` | Huecos de cobertura. Con `recommendations=false` no se llama al LLM (solo la lista); si el LLM falla se usan recomendaciones fijas por tipo de hueco | JWT + miembro |

---

## Integraciones

| Método | Ruta | Descripción | Auth |
|---|---|---|---|
| `POST` | `/v2/integrations/jira` | `{org_id, base_url, email, token, jql (por defecto "issuetype = Bug")}`: upsert → `{configured, base_url, email, jql}`. 400 si la URL base no pasa la validación | JWT + miembro |
| `GET` | `/v2/integrations/jira?org_id=` | Configuración Jira (nunca el token) | JWT + miembro |
| `POST` | `/v2/integrations/github` | `{org_id, installation_id, repo_full_name (owner/repo)}`: upsert → `{configured, repo_full_name, installation_id}`. Ver nota | JWT + miembro |
| `GET` | `/v2/integrations/github?org_id=` | Configuración GitHub de la org | JWT + miembro |

**Vinculación de GitHub.** Antes de guardar se comprueba que la cuenta dueña de la instalación coincide con el owner del repo (mitiga el confused-deputy entre tenants): 403 si no coincide o no se puede verificar, 503 si la GitHub App no está configurada en multitenant, 409 si la instalación ya está vinculada a otra org.

---

## Frontend ↔ Backend

El frontend Next.js llama a `/api/v2/*` (rutas proxy en `frontend/src/app/api/v2/**/route.ts`), que reenvían a `<NEXT_PUBLIC_API_BASE_URL>/v2/*` propagando el `Authorization`. La salud se expone en `/api/health` (proxy a `/v2/health`, sin `probe`). Funciones de cliente en `frontend/src/lib/api/endpoints.ts`; tipos en `frontend/src/lib/api/types.ts`.

Rutas del backend **sin proxy** en Next:

- Por diseño (las llama el CI, no el navegador): `POST /v2/ci/webhook`, `POST /v2/ci/ingest`.
- Con JWT, hoy «solo backend»: `POST /v2/triage/run/{run_id}/resolve`, `GET /v2/certificates/{run_id}/html` y `POST /v2/defects/ask`.

Páginas frontend: `/verify` (pública) · `/app` · `/app/assurance` · `/app/autopilot` · `/app/calibration` · `/app/continuity` · `/app/defects` · `/app/graph` · `/app/guia` · `/app/integrations` · `/app/knowledge` · `/app/onboarding` · `/app/org` · `/app/settings` · `/app/test-plan` · `/app/verify`.
