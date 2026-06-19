# Spec — Cableado del API `/v2` (multitenant) + repo clonable

**Fecha:** 2026-06-19
**Rama:** `feat/v2-api-wiring` (desde `redesign`)
**Fase del plan de concurso:** Fase 1, Incremento 1 (ver `doc/AUDITORIA_CONCURSO_MTP.md`)
**Decisión de entorno:** demo contra Supabase hospedado (elección del usuario).

---

## 1. Objetivo

Cerrar el gap crítico detectado en la auditoría: el frontend Next.js llama a `POST /api/v2/*` que el backend FastAPI **no expone**, y los módulos multitenant **no importan** en un entorno limpio (`ImportError` por constantes ausentes en `config.py` y dependencias no declaradas).

Al terminar este incremento:
1. El flujo **login → analizar → resultado estructurado** funciona de extremo a extremo contra Supabase.
2. `git clone` + `pip install -r requirements.txt` + `import` de todos los módulos **no falla**.
3. La suite de tests pasa **sin** depender de Supabase ni de Ollama (mocks).

## 2. Fuera de alcance (incrementos posteriores)

Fix de RAGAS (embeddings/async), `docker-compose` con stack real (API + frontend + Ollama), datos de demo, limpieza de `README`/`/health`/`logging`, borrar `app_legacy.py`, endurecer `sanitizer.py`, `FORCE RLS` y CI backend. Estos están planificados pero **no** en este incremento.

## 3. Arquitectura

Un único `APIRouter` nuevo en `src/api_v2.py`, incluido en la app FastAPI existente (`api.py` → `app.include_router(v2_router)`). No se crea un segundo servidor. Los servicios ya existen; este incremento solo añade la **capa de transporte HTTP**.

### 3.1. Inicialización perezosa (evita romper el arranque)

`TenantKBRepository.__init__` exige `DATABASE_URL` y crea `HuggingFaceEmbeddings` (pesado). Por tanto **no** se instancia en import-time. Se usa una dependencia FastAPI que construye un singleton perezoso:

- `get_repo()` → devuelve el `TenantKBRepository` (singleton). Si `DATABASE_URL`/`SUPABASE_URL` no están configurados → `HTTPException(503, "Multi-tenant KB not configured")`.
- `get_analyzer()` → devuelve `StructuredAnalyzer` (singleton; cliente Ollama, ligero).
- `get_current_user` se importa de `src.security` (su import es seguro aunque falte config: `SupabaseJWTVerifier()` solo fija el issuer).

`multi_tenant_enabled = bool(DATABASE_URL and SUPABASE_URL)` (helper en `config.py`).

### 3.2. Contratos de endpoints

Todos requieren `Authorization: Bearer <jwt>` → `Depends(get_current_user)` → `user.user_id`.

| Método | Ruta | Entrada | Servicio | Salida |
|---|---|---|---|---|
| POST | `/v2/analyze` | `AnalyzeV2Request{error_log, org_id?, top_k=8}` | `retrieve_context` → `StructuredAnalyzer.analyze` → `save_analysis` | `AnalyzeV2Response` |
| POST | `/v2/upload` | multipart: file + form `scope, org_id?, contribute_global` | `ingest_file` | `UploadResponse` |
| GET | `/v2/orgs` | — | `list_user_organizations` | `List[OrganizationResponse]` |
| POST | `/v2/orgs` | `CreateOrgRequest{name}` | `create_organization` | `OrganizationResponse` |
| POST | `/v2/orgs/join` | `JoinOrgRequest{join_code}` | `join_organization` | `OrganizationResponse` |
| GET | `/health` (ampliar en `api.py`) | — | — | `{status, model, multi_tenant_enabled}` |

### 3.3. Flujo de `/v2/analyze` (el central)

```
user = Depends(get_current_user)                         # JWT Supabase verificado
contexts = repo.retrieve_context(                        # List[dict]: chunk_id, scope, source_title, content, similarity
    user_id=user.user_id, query=req.error_log,
    org_id=req.org_id, top_k=req.top_k)
analysis = analyzer.analyze(error_log=req.error_log, contexts=contexts)  # dict 5 campos
source_scopes = orden único de scopes presentes en contexts  # p.ej. ["org","global"]
analysis_id = repo.save_analysis(
    user_id=user.user_id, org_id=req.org_id, input_error=req.error_log,
    output=analysis, confidence=analysis["confidence"], source_scopes=source_scopes)
return AnalyzeV2Response(
    analysis=StructuredAnalysisPayload(**analysis),
    sources=[ScopeSource(scope=c["scope"], source_title=c["source_title"], similarity=c["similarity"]) for c in contexts],
    source_scopes=source_scopes, analysis_id=analysis_id)
```

Nota: si `contexts` está vacío, `StructuredAnalyzer.analyze` ya devuelve un fallback honesto (confidence 0.2); `sources`/`source_scopes` quedan vacíos. No es error.

### 3.4. Manejo de errores

- Sin token / token inválido → 401 (ya lo da `get_current_user`).
- Multitenant no configurado → 503 con `detail` claro (vía `get_repo`).
- `ValueError` de los servicios (p.ej. "User is not a member of the specified organization", scope inválido) → 400 con `detail`.
- `join_code` inexistente → 404.
- Errores de psycopg/conexión → 502 con `detail` genérico (sin filtrar la cadena de conexión).

## 4. Clonabilidad

### 4.1. `src/config.py` — añadir (lectura desde env, defaults seguros)

```python
DATABASE_URL = os.getenv("DATABASE_URL", "")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "data", "uploads"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "8"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "")
```

(Verificado: `tenant_kb.py:17-24` importa `DATABASE_URL, DEFAULT_TOP_K, UPLOAD_DIR`; `security.py:11` importa `SUPABASE_URL, SUPABASE_JWKS_URL, SUPABASE_JWT_AUDIENCE`. `CHUNK_SIZE/OVERLAP/EMBEDDING_MODEL` ya existen.)

### 4.2. `requirements.txt` — añadir y **pinear** versiones

`psycopg[binary]`, `pgvector`, `pyjwt`, `python-multipart`, `requests`. Pinear todo el fichero a las versiones instaladas y verificadas.

### 4.3. Commitear los módulos `untracked`

`src/{tenant_kb,security,multitenant_models,structured_analyzer,scope_priority,sanitizer}.py`, `db/migrations/001_multitenant_kb.sql`, `tests/{test_scope_priority,test_sanitizer}.py`, y el nuevo `src/api_v2.py` + `tests/test_api_v2.py`. Actualizar `.env.example` con las nuevas claves.

## 5. Estrategia de testing (TDD)

`tests/test_api_v2.py` con `fastapi.testclient.TestClient`. Se **mockean** `TenantKBRepository` (vía override de `get_repo`), `get_current_user` (usuario fake) y `StructuredAnalyzer` (vía override de `get_analyzer`). Casos:

1. `POST /v2/analyze` sin token → 401.
2. `POST /v2/analyze` con repo mock devolviendo 2 contexts (org+global) → 200, `AnalyzeV2Response` válido, `source_scopes == ["org","global"]`, `sources` mapeados, `analysis_id` propagado.
3. `POST /v2/analyze` con `contexts=[]` → 200, fallback, `sources==[]`.
4. `GET /v2/orgs` → 200, lista mapeada a `OrganizationResponse`.
5. `POST /v2/orgs` con `name` inválido (<2) → 422 (validación Pydantic).
6. `POST /v2/orgs/join` con `join_code` desconocido (mock lanza) → 404.
7. `/v2/*` con multitenant **no** configurado (override `get_repo` que lanza 503) → 503.
8. `GET /health` → incluye `multi_tenant_enabled`.

No se requieren Supabase ni Ollama para la suite. Test e2e real queda documentado en runbook (§6) para ejecutar tras reactivar Supabase.

## 6. Acción requerida del usuario (Supabase hospedado)

El proyecto Supabase de `DATABASE_URL` no resuelve (pausado/borrado). Para verificación e2e:

1. Reactivar/recrear el proyecto en el dashboard de Supabase y actualizar `.env` + `frontend/.env.local` con la nueva `DATABASE_URL`/claves si cambian.
2. Aplicar la migración: `psql "$DATABASE_URL" -f db/migrations/001_multitenant_kb.sql` (o pegarla en el SQL Editor de Supabase).
3. Verificar: `uvicorn api:app` + frontend `npm run dev`, login con un usuario Supabase, crear org, subir un log, analizar.

Mientras tanto, el código queda construido y verde con mocks.

## 7. Entrega

PR pequeño desde `feat/v2-api-wiring`. Revisión con `code-reviewer` antes de cerrar. Commits siguiendo conventional commits (`feat:`, `test:`, `chore:`).

## 8. Criterios de aceptación

- [ ] `python -c "import src.api_v2, src.tenant_kb, src.security"` no lanza en entorno limpio con deps instaladas.
- [ ] `pytest -m "not integration"` verde, incluido `tests/test_api_v2.py`.
- [ ] `api.py` incluye el router; `GET /health` expone `multi_tenant_enabled`.
- [ ] El contrato de respuesta de `/v2/analyze` coincide exactamente con `frontend/src/lib/api/types.ts`.
- [ ] `.env.example` y `requirements.txt` actualizados (deps pinneadas).
