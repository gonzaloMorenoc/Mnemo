# Mnemo — Referencia de API (`/v2`)

Todos los endpoints `/v2` requieren `Authorization: Bearer <jwt-supabase>`, con cuatro excepciones públicas: `/v2/health`, `/v2/ci/webhook` (auth por firma HMAC), y los dos de verificación de actas — `POST /v2/certificates/verify` y `GET /v2/certificates/pubkey` — que son **públicos por diseño** (un auditor externo verifica sin cuenta).

Errores comunes: 401 sin token, 403 si el usuario no es miembro de la org, 404 recurso inexistente (run/certificado/familia), 409 conflicto (p.ej. instalación de GitHub ya vinculada a otra org), 413 subida o cuerpo por encima de la cota (`INGEST_MAX_BYTES` / `CI_MAX_BODY_BYTES`, 10 MiB por defecto), 422 validación, 400 datos malos, 500 fallo de render (PDF), 502 error de BD, 503 si el stack multitenant no está configurado.

El entrypoint de producción es `asgi:app` (`uvicorn asgi:app`). `api.py` no existe en el árbol de producción; el router v2 es el único montado.

---

## Orgs

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/orgs` | Lista las orgs del usuario autenticado | JWT |
| `POST` | `/v2/orgs` | Crea una org (el creador queda como `owner`) | JWT |
| `POST` | `/v2/orgs/join` | Se une a una org por `join_code` | JWT |

---

## Health

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/health` | Estado del backend + `multi_tenant_enabled` | Público |

---

## Ingest

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/ingest/report` | Ingiere un reporte de test (multipart: `file`, `project`, `source`, `org_id`) | JWT + miembro |
| `POST` | `/v2/ingest/jira/file` | Ingiere un export de Jira (multipart: `file`, `project`, `org_id`) | JWT + miembro |
| `POST` | `/v2/ingest/jira/pull` | Pull de issues de Jira vía API configurada (`org_id`, `project`) | JWT + miembro |
| `POST` | `/v2/ci/webhook` | Webhook de CI (artefacto JSON firmado; firma HMAC `X-Hub-Signature-256`) | HMAC |

Las tres rutas de subida aplican la cota `INGEST_MAX_BYTES` (413 si se excede). `/v2/ci/webhook` no usa JWT: exige firma HMAC válida (401), `CI_SERVICE_USER_ID` configurado (503) y, si `CI_SERVICE_ORG_ID` está definido, rechaza artefactos de otra org (403); el cuerpo se acota con `CI_MAX_BODY_BYTES` (413). La ingesta es idempotente por `(org_id, run_uid)`: reentregas devuelven `deduplicated: true`. Internamente encadena ingesta → triaje → certificado → gate; cada etapa degrada independientemente si falla.

---

## Defectos y Defect DNA

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/defects?org_id=` | Lista familias de defecto de una org | JWT + miembro |
| `GET` | `/v2/defects/{defect_id}` | Linaje de una familia (fallos a través de runs/proyectos) | JWT + miembro |
| `PATCH` | `/v2/defects/{family_id}/label` | Etiqueta una familia (`flaky`/`real`/`maintenance`/`infra`/`unknown`) | JWT + miembro |
| `POST` | `/v2/defects/{defect_id}/root-cause` | Análisis LLM de causa raíz (cacheable; `?regenerate=true` fuerza) | JWT + miembro |
| `POST` | `/v2/defects/ask` | Pregunta en lenguaje natural contra las familias de defecto (RAG semántico) | JWT + miembro |

---

## Triage (Autopilot — Nivel 1)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/triage/run/{run_id}` | Lista veredictos de triaje de un run | JWT + miembro |
| `POST` | `/v2/triage/run/{run_id}/resolve` | Resuelve tiebreaks pendientes del run | JWT + miembro |

---

## Assurance

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/assurance/run/{run_id}` | Veredicto de aseguramiento de un run (determinista + narrativa LLM opcional) | JWT + miembro |

El campo `risk` vale `"atencion"` si hay fallos nuevos (familias novel); si no, `"ok"`. `narrative` puede ser `null` si el proveedor LLM no está disponible (degradación elegante).

---

## Calibración (foso)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/calibration/metrics?org_id=` | Métricas del foso: precisión del motor, correcciones humanas, drift | JWT + miembro |

---

## Actions (Autopilot — Nivel 2)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/actions/run/{run_id}/propose` | Propone acciones (`quarantine`/`ticket`/`self_heal`) sobre los veredictos del run | JWT + miembro |
| `GET` | `/v2/actions?org_id=&status=` | Lista acciones de la org; `status` opcional ∈ `proposed`/`approved`/`rejected`/`materializing`/`materialized` (otro valor → 400) | JWT + miembro |
| `POST` | `/v2/actions/{action_id}/approve` | Aprueba y materializa una acción (quarantine → PR en GitHub) | JWT + miembro |
| `POST` | `/v2/actions/{action_id}/reject` | Rechaza una acción con motivo | JWT + miembro |

---

## Certificados (Autopilot — Nivel 3)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/certificates/run/{run_id}` | Genera el certificado firmado de release assurance | JWT + miembro |
| `GET` | `/v2/certificates/{run_id}` | Lee el certificado de un run (JSON) | JWT + miembro |
| `GET` | `/v2/certificates/{run_id}/html` | Renderiza el certificado en HTML | JWT + miembro |
| `GET` | `/v2/certificates/{run_id}/pdf` | Descarga el certificado en PDF | JWT + miembro |
| `GET` | `/v2/certificates/pubkey` | Clave pública Ed25519 de firma (`{algorithm, public_key_pem}`; 503 sin clave configurada) | **Público** |
| `POST` | `/v2/certificates/verify` | Verifica la firma de un certificado (`canonical_json` + `signature`) → `{valido}` | **Público** |

`verdict` ∈ `apto` / `apto-con-reservas` / `no-apto`. Los dos últimos endpoints son **públicos sin auth a propósito**: la verificación es criptografía pura y su valor está en que un tercero (cliente, auditor) pueda comprobar un acta sin cuenta en Mnemo — también desde la página `/verify` del frontend u offline con la clave pública.

---

## Gate (CI Quality Gate)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/gate/run/{run_id}` | Publica el resultado del gate en el commit status de GitHub | JWT + miembro |

---

## Briefing

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/runs/{run_id}/briefing` | Resumen ejecutivo de un run: veredicto, recomendación, highlights, citas (LLM, degrada) | JWT + miembro |

---

## Knowledge (Memoria QA)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/knowledge` | Crea un ítem de conocimiento (`regla_negocio`/`flujo`/`riesgo`/`glosario`/`leccion`/`reto`/`patron`) | JWT + miembro |
| `GET` | `/v2/knowledge?org_id=&kind=&domain=` | Lista ítems (filtros opcionales por kind y domain) | JWT + miembro |
| `GET` | `/v2/knowledge/{item_id}?org_id=` | Obtiene un ítem por id (`org_id` es query param **obligatorio** — 422 si falta) | JWT + miembro |
| `POST` | `/v2/knowledge/search` | Búsqueda semántica unificada (knowledge + defect families) | JWT + miembro |
| `POST` | `/v2/knowledge/ask` | Pregunta en lenguaje natural contra la base de conocimiento | JWT + miembro |

---

## Onboarding

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/onboarding/domain-summary` | Resumen del dominio de QA para incorporación de nuevos miembros | JWT + miembro |
| `POST` | `/v2/onboarding/learning-path` | Ruta de aprendizaje personalizada por tema | JWT + miembro |

---

## Test Plan

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/test-plan/generate` | Genera un plan de pruebas a partir de una HU (multipart: `org_id`, `case_format` — default `manual` —, y la fuente con prioridad `hu_text` > `jira_url` > `file`) | JWT + miembro |
| `POST` | `/v2/test-plan/export/xray` | Exporta el plan a Jira/Xray (Cloud o Server/DC) | JWT + miembro |

---

## Automation

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/automation/generate` | Genera un test Playwright (`.spec.ts`) desde un caso de prueba JSON | JWT (sin check duro de org) |
| `POST` | `/v2/automation/pr` | Abre un draft PR en el repo de la org añadiendo el fichero generado | JWT + miembro |

`/v2/automation/generate` usa los test assets de la org **solo como ejemplos few-shot de estilo**, con retrieval membership-gated: un miembro obtiene el test con el estilo del repo; un no-miembro obtiene el test sin ejemplos (no recibe 403).

---

## Repo (indexación de tests del cliente)

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/repo/index` | Indexa los tests del repo GitHub de la org como assets (body `{org_id}`; 503 GitHub sin configurar, 502 error de la API de GitHub) | JWT + miembro |
| `GET` | `/v2/repo/tests?org_id=` | Lista los test assets indexados de la org | JWT + miembro |

Los assets alimentan el estilo few-shot de `/v2/automation/generate` y el detector de gaps (`/v2/graph/gaps`).

---

## Graph

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/graph?org_id=&focus=&limit=` | Grafo de conocimiento (nodos: dominios, familias, ítems; aristas: relaciones); `limit` se capa a 500 en servidor | JWT + miembro |
| `GET` | `/v2/graph/gaps?org_id=` | Detecta huecos de cobertura en el grafo | JWT + miembro |

---

## Integrations

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/integrations/jira` | Configura (upsert) la integración Jira de la org | JWT + miembro |
| `GET` | `/v2/integrations/jira?org_id=` | Lee la configuración Jira de la org | JWT + miembro |
| `POST` | `/v2/integrations/github` | Configura (upsert) la GitHub App de la org | JWT + miembro |
| `GET` | `/v2/integrations/github?org_id=` | Lee la configuración GitHub de la org | JWT + miembro |

La integración Xray (migración `019`) reutiliza la tabla `org_integrations` con `provider='xray'`. No hay endpoints propios de Xray — el acceso es interno desde `/v2/test-plan/export/xray`.

---

## Frontend ↔ Backend

El frontend Next.js llama a `/api/v2/*` (rutas proxy en `app/api/v2/**`) que reenvían a `<NEXT_PUBLIC_API_BASE_URL>/v2/*` propagando el `Authorization`. Funciones de cliente en `frontend/src/lib/api/endpoints.ts`; tipos en `frontend/src/lib/api/types.ts`.

Tres endpoints con JWT son hoy "solo backend" (sin ruta proxy en Next): `POST /v2/triage/run/{run_id}/resolve`, `GET /v2/certificates/{run_id}/html` y `POST /v2/defects/ask`.

Páginas frontend activas: `/verify` (pública) · `/app` · `/app/assurance` · `/app/autopilot` · `/app/calibration` · `/app/defects` · `/app/graph` · `/app/integrations` · `/app/knowledge` · `/app/onboarding` · `/app/org` · `/app/settings` · `/app/test-plan`.
