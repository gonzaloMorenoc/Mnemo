# Mnemo — Referencia de API (`/v2`)

Todos los endpoints `/v2` (salvo `/v2/health` y `/v2/ci/webhook`) requieren `Authorization: Bearer <jwt-supabase>`. Errores comunes: 401 sin token, 403 si el usuario no es miembro de la org, 422 validación, 400 datos malos, 502 error de BD, 503 si el stack multitenant no está configurado.

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

`/v2/ci/webhook` no usa JWT. Internamente encadena ingesta → triaje → certificado → gate; cada etapa degrada independientemente si falla.

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

El campo `risk` vale `"atencion"` si hay fallos nuevos o reaparece una familia `resolved`; si no, `"ok"`. `narrative` puede ser `null` si Ollama no está disponible (degradación elegante).

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
| `GET` | `/v2/actions?org_id=&status=` | Lista acciones de la org (filtro opcional por status) | JWT + miembro |
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
| `POST` | `/v2/certificates/verify` | Verifica la firma de un certificado (`canonical_json` + `signature`) | JWT |

`verdict` ∈ `apto` / `apto-con-reservas` / `no-apto`.

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
| `GET` | `/v2/knowledge/{item_id}?org_id=` | Obtiene un ítem por id | JWT + miembro |
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
| `POST` | `/v2/test-plan/generate` | Genera un plan de pruebas a partir de una HU (texto directo, URL Jira o fichero) | JWT + miembro |
| `POST` | `/v2/test-plan/export/xray` | Exporta el plan a Jira/Xray (Cloud o Server/DC) | JWT + miembro |

---

## Automation

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `POST` | `/v2/automation/generate` | Genera un test Playwright (`.spec.ts`) desde un caso de prueba JSON | JWT (sin check de org) |
| `POST` | `/v2/automation/pr` | Abre un draft PR en el repo de la org añadiendo el fichero generado | JWT + miembro |

`/v2/automation/generate` no accede a datos de org, por lo que solo requiere JWT válido (sin verificación de membresía).

---

## Graph

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| `GET` | `/v2/graph?org_id=&focus=&limit=` | Grafo de conocimiento (nodos: dominios, familias, ítems; aristas: relaciones) | JWT + miembro |
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

Páginas frontend activas: `/app/assurance`, `/app/defects`, `/app/knowledge`, `/app/test-plan`, `/app/onboarding`, `/app/graph`.
