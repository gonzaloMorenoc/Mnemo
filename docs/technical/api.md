# Mnemo — Referencia de API (`/v2`)

Todos los endpoints `/v2` (salvo `/v2/health`) requieren `Authorization: Bearer <jwt-supabase>`. Errores comunes: 401 sin token, 403 si el usuario no es miembro de la org, 422 validación, 400 datos malos, 502 error de BD, 503 si el stack multitenant no está configurado.

## Mnemo — Aseguramiento y Defect DNA

### `POST /v2/ingest/report`
Ingiere un reporte de test y agrupa los fallos en familias.
- **Body** (multipart/form-data): `file` (reporte), `project` (str), `source` (`allure`|`junit`), `org_id` (str).
- **200** `IngestReportResponse`: `{ run_id, ingested, known, novel }`.
- `400` source desconocido o reporte malformado · `403` no-miembro.

### `GET /v2/defects?org_id=<id>`
Lista las familias de defecto de una org.
- **200** `DefectFamilyResponse[]`: `{ id, title, status, occurrence_count, first_seen, last_seen, projects[] }` (orden: ocurrencias desc).

### `GET /v2/defects/{id}`
Linaje de una familia (fallos a través de runs/proyectos).
- **200** `DefectLineageResponse`: `{ family: {id,title,status,occurrence_count} | null, failures: FailureRef[] }`.
- `family=null` si no existe o el usuario no es miembro de su org.

### `GET /v2/assurance/run/{run_id}`
Veredicto de aseguramiento de un run.
- **200** `AssuranceVerdictResponse`: `{ run_id, ingested, known, novel, risk, top_families: FamilyVerdict[], narrative }`.
  - `risk`: `"atencion"` si hay fallos nuevos (o reaparece una familia `resolved`), si no `"ok"`.
  - `top_families[]`: `{ id, title, occurrence_count, recurring }` (top 5 por ocurrencias; `recurring` = vista antes de este run).
  - `narrative`: resumen LLM, o **`null`** si el LLM (Ollama) no está disponible (degradación elegante).
- `404` si el run no existe o el usuario no es miembro de su org.

## Organizaciones y análisis (multitenant, base)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/v2/orgs` | Orgs del usuario |
| `POST` | `/v2/orgs` | Crear org (el creador queda `owner`) |
| `POST` | `/v2/orgs/join` | Unirse por `join_code` |
| `POST` | `/v2/analyze` | Análisis RAG estructurado (KB multitenant) |
| `POST` | `/v2/upload` | Subir conocimiento a la KB (scope user/org, opción contribuir a global) |
| `GET` | `/v2/health` | Estado + `multi_tenant_enabled` (público) |

## Frontend ↔ backend

El frontend Next.js llama a `/api/v2/*` (rutas proxy en `app/api/v2/**`) que reenvían a `<NEXT_PUBLIC_API_BASE_URL>/v2/*` propagando el `Authorization`. Funciones de cliente en `frontend/src/lib/api/endpoints.ts`; tipos en `frontend/src/lib/api/types.ts`.

## Endpoints legacy (single-tenant, en coexistencia)

`api.py` también expone el camino RAG original (sin multitenant): `POST /analyze`, `POST /sync`, `GET /history`, `GET /stats`, `POST /evaluate`, `GET /health`. Se mantienen hasta que el camino `/v2` los sustituya (ver ADR 0001).
