# v2 API Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer los servicios multitenant ya existentes vía un router FastAPI `/v2`, de modo que el frontend Next.js funcione de extremo a extremo y el repo importe sin `ImportError`.

**Architecture:** Un `APIRouter` nuevo (`src/api_v2.py`) montado en la app FastAPI existente (`api.py`), con inicialización perezosa de los servicios (singletons vía dependencias) y guardia 503 si el stack multitenant no está configurado. Auth por JWT de Supabase (`src.security.get_current_user`). Los endpoints mapean 1:1 a `TenantKBRepository` + `StructuredAnalyzer`.

**Tech Stack:** Python, FastAPI, Pydantic, psycopg + pgvector (Postgres), pyjwt (Supabase JWKS), pytest + TestClient.

**Branch:** `feat/v2-api-wiring` (ya creada). Spec: `docs/superpowers/specs/2026-06-19-v2-api-wiring-design.md`.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/config.py` (modificar) | Añadir `DATABASE_URL, UPLOAD_DIR, DEFAULT_TOP_K, SUPABASE_URL, SUPABASE_JWKS_URL, SUPABASE_JWT_AUDIENCE` + helper `multi_tenant_enabled()` |
| `src/api_v2.py` (crear) | Router `/v2`: dependencias perezosas + 5 endpoints + mappers |
| `api.py` (modificar) | `include_router(v2_router)` + `/health` con `multi_tenant_enabled` |
| `requirements.txt` (modificar) | Añadir deps multitenant y pinear versiones |
| `.env.example` (modificar) | Documentar las 6 claves nuevas |
| `tests/test_config.py` (crear) | Tests de constantes + helper + imports de módulos |
| `tests/test_api_v2.py` (crear) | Tests del router con mocks (sin Supabase/Ollama) |

---

## Task 1: Config constants + `multi_tenant_enabled` helper

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import importlib


def test_config_defines_multitenant_constants():
    import src.config as config
    importlib.reload(config)
    # Las constantes existen y tienen defaults seguros (string vacío / int)
    assert hasattr(config, "DATABASE_URL")
    assert hasattr(config, "UPLOAD_DIR")
    assert isinstance(config.DEFAULT_TOP_K, int) and config.DEFAULT_TOP_K >= 1
    assert hasattr(config, "SUPABASE_URL")
    assert hasattr(config, "SUPABASE_JWKS_URL")
    assert hasattr(config, "SUPABASE_JWT_AUDIENCE")


def test_multi_tenant_enabled_false_when_unset(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    assert config.multi_tenant_enabled() is False


def test_multi_tenant_enabled_true_when_set(monkeypatch):
    import src.config as config
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    assert config.multi_tenant_enabled() is True


def test_multitenant_modules_import():
    # No deben lanzar ImportError en un entorno con deps instaladas
    import src.tenant_kb  # noqa: F401
    import src.security  # noqa: F401
    import src.structured_analyzer  # noqa: F401
    import src.multitenant_models  # noqa: F401
    import src.sanitizer  # noqa: F401
    import src.scope_priority  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError`/`ImportError` (las constantes y el helper aún no existen).

- [ ] **Step 3: Add the constants and helper to `src/config.py`**

Añadir al final de `src/config.py` (después del bloque de Confluence):

```python
# Multi-tenant KB (Postgres + Supabase). Defaults vacios = modo single-tenant.
DATABASE_URL = os.getenv("DATABASE_URL", "")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "data", "uploads"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "8"))

# Supabase auth (verificacion JWT via JWKS)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "")


def multi_tenant_enabled() -> bool:
    """True solo si hay BD Postgres y Supabase configurados."""
    return bool(DATABASE_URL and SUPABASE_URL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add multi-tenant config constants and multi_tenant_enabled helper"
```

---

## Task 2: Dependencies, `.env.example`, and version the untracked modules

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Add to git: `src/{tenant_kb,security,multitenant_models,structured_analyzer,scope_priority,sanitizer}.py`, `db/migrations/001_multitenant_kb.sql`, `tests/{test_scope_priority,test_sanitizer}.py`

- [ ] **Step 1: Add and pin dependencies**

Añadir estas líneas a `requirements.txt` (las deps que faltan para el stack multitenant):

```
psycopg[binary]
pgvector
pyjwt
python-multipart
requests
```

Luego **pinear todo** el fichero a las versiones instaladas. Ejecuta y revisa:

```bash
# Ver versiones instaladas de cada dependencia directa
pip show psycopg pgvector pyjwt python-multipart requests langchain ragas chromadb 2>/dev/null | grep -E "^(Name|Version)"
```

Edita `requirements.txt` para que cada línea quede como `paquete==X.Y.Z` con la versión reportada (las que ya estaban y las nuevas). No dejar ninguna línea sin versión.

- [ ] **Step 2: Update `.env.example`**

Añadir al final de `.env.example`:

```
# Multi-tenant KB (Postgres) + Supabase Auth
DATABASE_URL=postgresql://user:pass@host:5432/postgres
UPLOAD_DIR=./data/uploads
DEFAULT_TOP_K=8
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_JWT_AUDIENCE=authenticated
```

- [ ] **Step 3: Verify a clean install resolves and imports work**

Run:
```bash
pip install -r requirements.txt
python -c "import src.tenant_kb, src.security, src.structured_analyzer, src.multitenant_models; print('imports OK')"
```
Expected: `imports OK` sin trazas.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example \
  src/tenant_kb.py src/security.py src/multitenant_models.py \
  src/structured_analyzer.py src/scope_priority.py src/sanitizer.py \
  db/migrations/001_multitenant_kb.sql \
  tests/test_scope_priority.py tests/test_sanitizer.py
git commit -m "chore: pin deps, document env vars, and version multi-tenant modules"
```

---

## Task 3: `/v2/analyze` endpoint (router skeleton + analyze)

**Files:**
- Create: `src/api_v2.py`
- Test: `tests/test_api_v2.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_v2.py`:

```python
from typing import List
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="user-123", email="t@example.com", claims={})


def make_client(*, repo=None, analyzer=None, with_user=True) -> TestClient:
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_repo] = lambda: repo
    if analyzer is not None:
        app.dependency_overrides[api_v2.get_analyzer] = lambda: analyzer
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _fake_user
    return TestClient(app)


def _ctx(scope, title, sim):
    return {
        "chunk_id": "c1", "document_id": "d1", "scope": scope,
        "owner_user_id": None, "org_id": None,
        "source_title": title, "content": "boom", "similarity": sim,
    }


def test_analyze_requires_auth():
    # Sin override de usuario y sin token -> 401
    client = make_client(repo=MagicMock(), analyzer=MagicMock(), with_user=False)
    resp = client.post("/v2/analyze", json={"error_log": "TimeoutException at line 10"})
    assert resp.status_code == 401


def test_analyze_happy_path_maps_response():
    repo = MagicMock()
    repo.retrieve_context.return_value = [_ctx("org", "ticket-1", 0.9), _ctx("global", "kb-doc", 0.7)]
    repo.save_analysis.return_value = 42
    analyzer = MagicMock()
    analyzer.analyze.return_value = {
        "root_cause": "rc", "why_it_happened": "why", "how_to_fix": "fix",
        "suggested_patch_steps": ["s1"], "confidence": 0.8,
    }
    client = make_client(repo=repo, analyzer=analyzer)
    resp = client.post("/v2/analyze", json={"error_log": "TimeoutException at line 10", "org_id": "org-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis"]["root_cause"] == "rc"
    assert body["source_scopes"] == ["org", "global"]
    assert len(body["sources"]) == 2
    assert body["sources"][0] == {"scope": "org", "source_title": "ticket-1", "similarity": 0.9}
    assert body["analysis_id"] == 42


def test_analyze_empty_contexts_returns_fallback():
    repo = MagicMock()
    repo.retrieve_context.return_value = []
    repo.save_analysis.return_value = 7
    analyzer = MagicMock()
    analyzer.analyze.return_value = {
        "root_cause": "Insufficient context", "why_it_happened": "x", "how_to_fix": "y",
        "suggested_patch_steps": [], "confidence": 0.2,
    }
    client = make_client(repo=repo, analyzer=analyzer)
    resp = client.post("/v2/analyze", json={"error_log": "weird error here"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == []
    assert body["source_scopes"] == []


def test_analyze_503_when_not_configured(monkeypatch):
    # Sin override de get_repo y multitenant deshabilitado -> 503
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: False)
    client = make_client(analyzer=MagicMock())  # solo override user + analyzer
    resp = client.post("/v2/analyze", json={"error_log": "TimeoutException at line 10"})
    assert resp.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_v2.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api_v2'`.

- [ ] **Step 3: Create `src/api_v2.py` with skeleton + `/v2/analyze`**

```python
from typing import Any, Dict, List

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from src.config import multi_tenant_enabled
from src.multitenant_models import (
    AnalyzeV2Request,
    AnalyzeV2Response,
    ScopeSource,
    StructuredAnalysisPayload,
)
from src.security import AuthenticatedUser, get_current_user
from src.structured_analyzer import StructuredAnalyzer
from src.tenant_kb import TenantKBRepository

router = APIRouter(prefix="/v2", tags=["v2"])

# Singletons perezosos (sin anotacion PEP 604 para compatibilidad <3.10)
_repo = None
_analyzer = None


def get_repo() -> TenantKBRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _repo
    if _repo is None:
        _repo = TenantKBRepository()
    return _repo


def get_analyzer() -> StructuredAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = StructuredAnalyzer()
    return _analyzer


def _unique_scopes(contexts: List[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for c in contexts:
        if c["scope"] not in seen:
            seen.append(c["scope"])
    return seen


@router.post("/analyze", response_model=AnalyzeV2Response)
def analyze_v2(
    req: AnalyzeV2Request,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
    analyzer: StructuredAnalyzer = Depends(get_analyzer),
) -> AnalyzeV2Response:
    try:
        contexts = repo.retrieve_context(
            user_id=user.user_id, query=req.error_log, org_id=req.org_id, top_k=req.top_k
        )
        analysis = analyzer.analyze(error_log=req.error_log, contexts=contexts)
        source_scopes = _unique_scopes(contexts)
        analysis_id = repo.save_analysis(
            user_id=user.user_id,
            org_id=req.org_id,
            input_error=req.error_log,
            output=analysis,
            confidence=float(analysis["confidence"]),
            source_scopes=source_scopes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc

    return AnalyzeV2Response(
        analysis=StructuredAnalysisPayload(**analysis),
        sources=[
            ScopeSource(scope=c["scope"], source_title=c["source_title"], similarity=c["similarity"])
            for c in contexts
        ],
        source_scopes=source_scopes,
        analysis_id=analysis_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_v2.py -v`
Expected: PASS (4 tests de analyze).

- [ ] **Step 5: Commit**

```bash
git add src/api_v2.py tests/test_api_v2.py
git commit -m "feat: add /v2/analyze endpoint wiring TenantKB + StructuredAnalyzer"
```

---

## Task 4: `/v2/orgs` endpoints (list, create, join)

**Files:**
- Modify: `src/api_v2.py`
- Test: `tests/test_api_v2.py`

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/test_api_v2.py`:

```python
def _org(role="member"):
    return {"id": "org-1", "name": "Acme QA", "join_code": "ABC123", "role": role, "created_at": "2026-06-19T10:00:00"}


def test_list_orgs_maps_response():
    repo = MagicMock()
    repo.list_user_organizations.return_value = [_org("owner")]
    client = make_client(repo=repo)
    resp = client.get("/v2/orgs")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "org-1"
    assert body[0]["role"] == "owner"


def test_create_org_validation_error():
    repo = MagicMock()
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "x"})  # min_length=2
    assert resp.status_code == 422


def test_create_org_happy_path():
    repo = MagicMock()
    repo.create_organization.return_value = _org("owner")
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs", json={"name": "Acme QA"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme QA"


def test_join_org_unknown_code_returns_404():
    repo = MagicMock()
    repo.join_organization.side_effect = ValueError("Could not join organization with the provided code")
    client = make_client(repo=repo)
    resp = client.post("/v2/orgs/join", json={"join_code": "BADCODE"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_v2.py -k "org" -v`
Expected: FAIL — 404 routes no existen (los endpoints `/v2/orgs*` aún no están).

- [ ] **Step 3: Add org endpoints to `src/api_v2.py`**

Añadir el import de modelos (ampliar la línea de import existente):

```python
from src.multitenant_models import (
    AnalyzeV2Request,
    AnalyzeV2Response,
    CreateOrgRequest,
    JoinOrgRequest,
    OrganizationResponse,
    ScopeSource,
    StructuredAnalysisPayload,
)
```

Añadir el mapper y los endpoints al final del fichero:

```python
def _org_to_response(org: Dict[str, Any]) -> OrganizationResponse:
    return OrganizationResponse(
        id=str(org["id"]),
        name=org["name"],
        join_code=org["join_code"],
        role=org.get("role"),
        created_at=str(org["created_at"]) if org.get("created_at") is not None else None,
    )


@router.get("/orgs", response_model=List[OrganizationResponse])
def list_orgs(
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> List[OrganizationResponse]:
    try:
        orgs = repo.list_user_organizations(user_id=user.user_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [_org_to_response(o) for o in orgs]


@router.post("/orgs", response_model=OrganizationResponse)
def create_org(
    req: CreateOrgRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> OrganizationResponse:
    try:
        org = repo.create_organization(user_id=user.user_id, name=req.name)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return _org_to_response(org)


@router.post("/orgs/join", response_model=OrganizationResponse)
def join_org(
    req: JoinOrgRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> OrganizationResponse:
    try:
        org = repo.join_organization(user_id=user.user_id, join_code=req.join_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return _org_to_response(org)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_v2.py -v`
Expected: PASS (todos: analyze + orgs).

- [ ] **Step 5: Commit**

```bash
git add src/api_v2.py tests/test_api_v2.py
git commit -m "feat: add /v2/orgs list/create/join endpoints"
```

---

## Task 5: `/v2/upload` endpoint

**Files:**
- Modify: `src/api_v2.py`
- Test: `tests/test_api_v2.py`

- [ ] **Step 1: Write the failing test**

Añadir a `tests/test_api_v2.py`:

```python
from src.tenant_kb import IngestionResult


def test_upload_happy_path():
    repo = MagicMock()
    repo.ingest_file.return_value = IngestionResult(
        document_id="doc-1", chunk_count=3, global_document_id=None, storage_path="/uploads/user-123/a.log"
    )
    client = make_client(repo=repo)
    resp = client.post(
        "/v2/upload",
        data={"scope": "user", "contribute_global": "false"},
        files={"file": ("a.log", b"NullPointerException at Foo.java:42", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc-1"
    assert body["chunk_count"] == 3
    # Verifica que se reenviaron los bytes y el scope al servicio
    kwargs = repo.ingest_file.call_args.kwargs
    assert kwargs["scope"] == "user"
    assert kwargs["filename"] == "a.log"
    assert kwargs["data"] == b"NullPointerException at Foo.java:42"


def test_upload_org_scope_without_org_id_is_400():
    repo = MagicMock()
    repo.ingest_file.side_effect = ValueError("org_id is required when scope is 'org'")
    client = make_client(repo=repo)
    resp = client.post(
        "/v2/upload",
        data={"scope": "org", "contribute_global": "false"},
        files={"file": ("a.log", b"some error log content", "text/plain")},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_v2.py -k upload -v`
Expected: FAIL — endpoint `/v2/upload` no existe (404).

- [ ] **Step 3: Add the upload endpoint to `src/api_v2.py`**

Ampliar el import de FastAPI (primera línea de fastapi):

```python
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
```

Añadir el import del modelo `UploadResponse` a la lista de `src.multitenant_models` y el import de `Optional`:

```python
from typing import Any, Dict, List, Optional
```
```python
from src.multitenant_models import (
    AnalyzeV2Request,
    AnalyzeV2Response,
    CreateOrgRequest,
    JoinOrgRequest,
    OrganizationResponse,
    ScopeSource,
    StructuredAnalysisPayload,
    UploadResponse,
)
```

Añadir el endpoint al final del fichero:

```python
@router.post("/upload", response_model=UploadResponse)
def upload_v2(
    file: UploadFile = File(...),
    scope: str = Form("user"),
    org_id: Optional[str] = Form(None),
    contribute_global: bool = Form(False),
    user: AuthenticatedUser = Depends(get_current_user),
    repo: TenantKBRepository = Depends(get_repo),
) -> UploadResponse:
    data = file.file.read()
    try:
        result = repo.ingest_file(
            user_id=user.user_id,
            filename=file.filename or "upload.txt",
            data=data,
            scope=scope,
            org_id=org_id,
            contribute_global=contribute_global,
            mime_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc

    return UploadResponse(
        document_id=str(result.document_id),
        global_document_id=str(result.global_document_id) if result.global_document_id else None,
        chunk_count=result.chunk_count,
        storage_path=result.storage_path,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_v2.py -v`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add src/api_v2.py tests/test_api_v2.py
git commit -m "feat: add /v2/upload endpoint"
```

---

## Task 6: Mount router in `api.py` + extend `/health`

**Files:**
- Modify: `api.py`
- Test: `tests/test_api_v2.py` (un test del router de health montado en app aislada NO aplica; ver nota)

- [ ] **Step 1: Write the failing test for the health router**

Para no disparar el `startup` pesado de `api.py`, añadimos el campo `multi_tenant_enabled` a `/health` a través del router `/v2` reutilizable. Añadir a `tests/test_api_v2.py`:

```python
def test_health_reports_multi_tenant_flag(monkeypatch):
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: True)
    client = make_client(with_user=False)  # /v2/health no requiere auth
    resp = client.get("/v2/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["multi_tenant_enabled"] is True
    assert "status" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api_v2.py -k health -v`
Expected: FAIL — `/v2/health` no existe (404).

- [ ] **Step 3: Add `/v2/health` to `src/api_v2.py`**

Añadir al final del fichero:

```python
@router.get("/health")
def health_v2() -> Dict[str, Any]:
    return {"status": "active", "multi_tenant_enabled": multi_tenant_enabled()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_api_v2.py -k health -v`
Expected: PASS.

- [ ] **Step 5: Mount the router and extend the legacy `/health` in `api.py`**

En `api.py`, tras la creación de `app = FastAPI(...)`, añadir:

```python
from src.api_v2 import router as v2_router
from src.config import multi_tenant_enabled

app.include_router(v2_router)
```

Y en el handler `/health` existente (`api.py:126-128`), modificar el `return` para incluir el flag:

```python
@app.get("/health")
def health():
    return {"status": "active", "model": "DeepSeek-R1", "multi_tenant_enabled": multi_tenant_enabled()}
```

- [ ] **Step 6: Verify `api.py` imports and mounts the router (no startup)**

Run:
```bash
python -c "import api; routes = [r.path for r in api.app.routes]; assert '/v2/analyze' in routes and '/v2/orgs' in routes, routes; print('router mounted:', sorted(p for p in routes if p.startswith('/v2')))"
```
Expected: imprime las rutas `/v2/*` montadas. (Importar `api` no dispara `startup`; solo se ejecuta con un servidor/cliente de contexto.)

- [ ] **Step 7: Commit**

```bash
git add api.py src/api_v2.py tests/test_api_v2.py
git commit -m "feat: mount /v2 router in app and expose multi_tenant_enabled in health"
```

---

## Task 7: Full suite, lint, and code review

**Files:** ninguno nuevo (verificación).

- [ ] **Step 1: Run the full unit suite**

Run: `python -m pytest -m "not integration" -v`
Expected: PASS — incluye `test_config.py`, `test_api_v2.py`, `test_scope_priority.py`, `test_sanitizer.py`, y los unit de `test_evaluation.py`.

- [ ] **Step 2: Clean-import check (no ImportError)**

Run: `python -c "import src.api_v2, src.tenant_kb, src.security, api; print('all imports OK')"`
Expected: `all imports OK`.

- [ ] **Step 3: Code review**

Lanzar el agente `code-reviewer` sobre el diff de la rama (`git diff redesign...feat/v2-api-wiring`). Atender CRITICAL/HIGH; corregir MEDIUM si es barato. Confirmar que el contrato de `/v2/analyze` coincide con `frontend/src/lib/api/types.ts` (`AnalysisResponse`/`ScopeSource`).

- [ ] **Step 4: Final commit (si el review introduce cambios)**

```bash
git add -A
git commit -m "refactor: address code review for /v2 wiring"
```

---

## Verification of e2e (post-Supabase, fuera de este plan automatizado)

Cuando el usuario reactive Supabase: aplicar `db/migrations/001_multitenant_kb.sql`, levantar `uvicorn api:app` + frontend, y validar login → crear org → upload → analizar. Documentado en el spec §6.
