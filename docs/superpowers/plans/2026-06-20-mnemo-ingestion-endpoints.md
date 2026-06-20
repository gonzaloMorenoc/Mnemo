# Mnemo — Servicio de ingesta + endpoints (Plan 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unir el núcleo (parsers/fingerprint, Plan 1) con la persistencia (repositorio, Plan 2) en un `IngestionService` (parse→sanitize→fingerprint→embed→`ingest_run`), y exponerlo por HTTP: `POST /v2/ingest/report`, `GET /v2/defects`, `GET /v2/defects/{id}`.

**Architecture:** `IngestionService` orquesta módulos puros + un `Embedder` inyectable (HF local, perezoso). Endpoints nuevos en `src/api_v2.py` con dependencias perezosas (guard 503) y auth Supabase. Tests con repo/embedder/service mockeados (sin BD/LLM); patrón de `tests/test_api_v2.py`.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest. Embeddings HF locales (mockeables). Reusa `src/sanitizer.py` (`sanitize_text`).

**Branch:** `feat/mnemo-assurance`. `python3` desde la raíz `/Users/gonzalo/Documents/GitHub/SmartErrorDebugger`. NO correr la suite completa con `-m integration` (toca BD); usar la unitaria.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/multitenant_models.py` (extender) | `IngestReportResponse`, `DefectFamilyResponse`, `FailureRef`, `DefectFamilySummary`, `DefectLineageResponse` |
| `src/defects/embedder.py` | `Embedder` (Protocol) + `LocalEmbedder` (HF perezoso) |
| `src/defects/ingestion_service.py` | `IngestionService.ingest_report(...)` |
| `src/api_v2.py` (extender) | deps `get_assurance_repo`/`get_ingestion_service` + 3 endpoints |
| `tests/test_ingestion_service.py` | tests del servicio (repo/embedder fake) |
| `tests/test_api_v2_defects.py` | tests de los 3 endpoints (mock) |

---

## Task 1: Modelos Pydantic de respuesta

**Files:**
- Modify: `src/multitenant_models.py`
- Test: `tests/test_assurance_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_assurance_models.py`:
```python
from src.multitenant_models import (
    IngestReportResponse, DefectFamilyResponse, FailureRef,
    DefectFamilySummary, DefectLineageResponse,
)


def test_ingest_report_response():
    r = IngestReportResponse(run_id="r1", ingested=3, known=1, novel=2)
    assert r.run_id == "r1" and r.novel == 2


def test_defect_family_response_defaults():
    f = DefectFamilyResponse(id="f1", title="Timeout", status="open", occurrence_count=2)
    assert f.projects == [] and f.first_seen is None


def test_defect_lineage_response():
    lin = DefectLineageResponse(
        family=DefectFamilySummary(id="f1", title="T", status="open", occurrence_count=1),
        failures=[FailureRef(id="x", test_name="t", project="p", source="allure")],
    )
    assert lin.family.id == "f1" and lin.failures[0].source == "allure"


def test_defect_lineage_response_empty():
    lin = DefectLineageResponse()
    assert lin.family is None and lin.failures == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_assurance_models.py -v`
Expected: FAIL — `ImportError` (models no existen).

- [ ] **Step 3: Append models to `src/multitenant_models.py`**

```python
class IngestReportResponse(BaseModel):
    run_id: str
    ingested: int
    known: int
    novel: int


class DefectFamilyResponse(BaseModel):
    id: str
    title: str
    status: str
    occurrence_count: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    projects: List[str] = Field(default_factory=list)


class FailureRef(BaseModel):
    id: str
    test_name: str
    error_type: Optional[str] = None
    project: str
    source: str
    created_at: Optional[str] = None


class DefectFamilySummary(BaseModel):
    id: str
    title: str
    status: str
    occurrence_count: int


class DefectLineageResponse(BaseModel):
    family: Optional[DefectFamilySummary] = None
    failures: List[FailureRef] = Field(default_factory=list)
```
(`Field`, `Optional`, `List`, `BaseModel` ya están importados en el fichero.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_assurance_models.py -v`
Expected: PASS (4).

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/multitenant_models.py tests/test_assurance_models.py
git commit -m "feat: add Mnemo assurance response models"
```

---

## Task 2: Embedder (interfaz + local perezoso)

**Files:**
- Create: `src/defects/embedder.py`
- Test: `tests/test_embedder.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_embedder.py`:
```python
from src.defects.embedder import Embedder, LocalEmbedder


def test_local_embedder_is_embedder_protocol():
    emb = LocalEmbedder()
    # No cargamos el modelo HF aqui: solo verificamos la interfaz y la inicializacion perezosa
    assert hasattr(emb, "embed")
    assert emb._hf is None  # no cargado hasta el primer embed


def test_fake_embedder_satisfies_protocol():
    class Fake:
        def embed(self, text: str):
            return [1.0, 2.0]

    def use(e: Embedder):
        return e.embed("x")

    assert use(Fake()) == [1.0, 2.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/defects/embedder.py`**

```python
from typing import List, Protocol, runtime_checkable

from src.config import EMBEDDING_MODEL


@runtime_checkable
class Embedder(Protocol):
    def embed(self, text: str) -> List[float]: ...


class LocalEmbedder:
    """Embedder local (HuggingFace). Carga el modelo de forma perezosa (no en import)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self._model_name = model_name
        self._hf = None

    def embed(self, text: str) -> List[float]:
        if self._hf is None:
            from langchain_huggingface import HuggingFaceEmbeddings
            self._hf = HuggingFaceEmbeddings(model_name=self._model_name)
        return self._hf.embed_query(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_embedder.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/defects/embedder.py tests/test_embedder.py
git commit -m "feat: add Embedder protocol and lazy LocalEmbedder"
```

---

## Task 3: IngestionService

**Files:**
- Create: `src/defects/ingestion_service.py`
- Test: `tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingestion_service.py`:
```python
import json

import pytest

from src.defects.ingestion_service import IngestionService


class FakeEmbedder:
    def embed(self, text: str):
        return [0.1, 0.2]


class FakeRepo:
    def __init__(self):
        self.calls = []

    def ingest_run(self, **kwargs):
        self.calls.append(kwargs)
        items = kwargs["items"]
        return {"run_id": "r1", "ingested": len(items), "known": 0, "novel": len(items)}


def test_ingest_report_parses_sanitizes_embeds_and_delegates():
    repo = FakeRepo()
    svc = IngestionService(repo=repo, embedder=FakeEmbedder())
    data = json.dumps([{
        "name": "test_login", "status": "failed",
        "statusDetails": {"message": "TimeoutException at host 10.0.0.1", "trace": "at A.java:1"},
    }]).encode()
    out = svc.ingest_report(user_id="u", org_id="o", project="proj-a", source="allure", data=data)
    assert out["ingested"] == 1
    item = repo.calls[0]["items"][0]
    assert "10.0.0.1" not in item.rec.message  # la IP fue sanitizada
    assert item.fingerprint and item.embedding == [0.1, 0.2]
    assert repo.calls[0]["org_id"] == "o" and repo.calls[0]["project"] == "proj-a"


def test_ingest_report_rejects_unknown_source():
    svc = IngestionService(repo=FakeRepo(), embedder=FakeEmbedder())
    with pytest.raises(ValueError):
        svc.ingest_report(user_id="u", org_id="o", project="p", source="xml", data=b"[]")


def test_ingest_report_empty_report_yields_zero():
    repo = FakeRepo()
    svc = IngestionService(repo=repo, embedder=FakeEmbedder())
    out = svc.ingest_report(user_id="u", org_id="o", project="p", source="allure", data=b"[]")
    assert out["ingested"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ingestion_service.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/defects/ingestion_service.py`**

```python
from dataclasses import replace
from typing import Any, Dict

from src.defects.embedder import Embedder
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.allure import parse_allure
from src.ingest.junit import parse_junit
from src.sanitizer import sanitize_text

_PARSERS = {"allure": parse_allure, "junit": parse_junit}


class IngestionService:
    def __init__(self, *, repo: AssuranceRepository, embedder: Embedder):
        self.repo = repo
        self.embedder = embedder

    def ingest_report(self, *, user_id: str, org_id: str, project: str, source: str, data: bytes) -> Dict[str, Any]:
        parser = _PARSERS.get(source)
        if parser is None:
            raise ValueError(f"unsupported source: {source}")
        records = parser(data, project=project)
        items = []
        for rec in records:
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            embedding = self.embedder.embed(f"{clean.error_type or ''} {message}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=embedding))
        return self.repo.ingest_run(
            user_id=user_id, org_id=org_id, project=project, source=source, items=items
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ingestion_service.py -v`
Expected: PASS (3). (Si `sanitize_text` no redacta la IP, revisar — pero el patrón IPv4 está en `src/sanitizer.py`.)

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/defects/ingestion_service.py tests/test_ingestion_service.py
git commit -m "feat: add IngestionService (parse->sanitize->fingerprint->embed->ingest_run)"
```

---

## Task 4: Endpoints `/v2/ingest/report`, `/v2/defects`, `/v2/defects/{id}`

**Files:**
- Modify: `src/api_v2.py`
- Test: `tests/test_api_v2_defects.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_v2_defects.py`:
```python
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(*, repo=None, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if service is not None:
        app.dependency_overrides[api_v2.get_ingestion_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_ingest_report_happy():
    service = MagicMock()
    service.ingest_report.return_value = {"run_id": "r1", "ingested": 2, "known": 1, "novel": 1}
    client = make_client(service=service)
    resp = client.post(
        "/v2/ingest/report",
        data={"project": "proj-a", "source": "allure", "org_id": "org-1"},
        files={"file": ("r.json", b"[]", "application/json")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "ingested": 2, "known": 1, "novel": 1}
    kw = service.ingest_report.call_args.kwargs
    assert kw["org_id"] == "org-1" and kw["source"] == "allure" and kw["data"] == b"[]"


def test_ingest_report_unknown_source_is_400():
    service = MagicMock()
    service.ingest_report.side_effect = ValueError("unsupported source: xml")
    client = make_client(service=service)
    resp = client.post("/v2/ingest/report",
                       data={"project": "p", "source": "xml", "org_id": "o"},
                       files={"file": ("r", b"[]", "application/json")})
    assert resp.status_code == 400


def test_ingest_report_non_member_is_403():
    service = MagicMock()
    service.ingest_report.side_effect = PermissionError("not a member")
    client = make_client(service=service)
    resp = client.post("/v2/ingest/report",
                       data={"project": "p", "source": "allure", "org_id": "o"},
                       files={"file": ("r", b"[]", "application/json")})
    assert resp.status_code == 403


def test_ingest_report_requires_auth():
    client = make_client(service=MagicMock(), with_user=False)
    resp = client.post("/v2/ingest/report",
                       data={"project": "p", "source": "allure", "org_id": "o"},
                       files={"file": ("r", b"[]", "application/json")})
    assert resp.status_code == 401


def test_list_defects_maps_response():
    repo = MagicMock()
    repo.list_defects.return_value = [{
        "id": "f1", "title": "Timeout", "status": "open", "occurrence_count": 2,
        "first_seen": "2026-06-19T10:00:00", "last_seen": "2026-06-20T10:00:00",
        "projects": ["proj-a", "proj-b"],
    }]
    client = make_client(repo=repo)
    resp = client.get("/v2/defects", params={"org_id": "org-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "f1" and body[0]["projects"] == ["proj-a", "proj-b"]
    assert repo.list_defects.call_args.kwargs["org_id"] == "org-1"


def test_defect_lineage_maps_response():
    repo = MagicMock()
    repo.get_lineage.return_value = {
        "family": {"id": "f1", "title": "Timeout", "status": "open", "occurrence_count": 2},
        "failures": [{"id": "x", "test_name": "t", "error_type": "TimeoutException",
                      "project": "proj-a", "source": "allure", "created_at": "2026-06-19T10:00:00"}],
    }
    client = make_client(repo=repo)
    resp = client.get("/v2/defects/f1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["family"]["id"] == "f1"
    assert body["failures"][0]["project"] == "proj-a"


def test_defect_lineage_not_found_returns_empty_family():
    repo = MagicMock()
    repo.get_lineage.return_value = {"family": None, "failures": []}
    client = make_client(repo=repo)
    resp = client.get("/v2/defects/missing")
    assert resp.status_code == 200
    assert resp.json()["family"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v2_defects.py -v`
Expected: FAIL — `AttributeError: module 'src.api_v2' has no attribute 'get_assurance_repo'` (o 404 en las rutas).

- [ ] **Step 3: Edit `src/api_v2.py`**

(a) Ampliar el import de `src.multitenant_models` para incluir:
`IngestReportResponse, DefectFamilyResponse, FailureRef, DefectFamilySummary, DefectLineageResponse` (mantener los existentes).

(b) Añadir imports nuevos cerca de los otros imports internos:
```python
from src.defects.repository import AssuranceRepository
from src.defects.ingestion_service import IngestionService
```

(c) Añadir dependencias perezosas (junto a `get_repo`/`get_analyzer`):
```python
_assurance_repo = None
_ingestion_service = None


def get_assurance_repo() -> AssuranceRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _assurance_repo
    if _assurance_repo is None:
        _assurance_repo = AssuranceRepository()
    return _assurance_repo


def get_ingestion_service() -> IngestionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _ingestion_service
    if _ingestion_service is None:
        from src.defects.embedder import LocalEmbedder
        _ingestion_service = IngestionService(repo=get_assurance_repo(), embedder=LocalEmbedder())
    return _ingestion_service
```

(d) Añadir los 3 endpoints al final del fichero:
```python
@router.post("/ingest/report", response_model=IngestReportResponse)
def ingest_report_v2(
    file: UploadFile = File(...),
    project: str = Form(...),
    source: str = Form(...),
    org_id: str = Form(...),
    user: AuthenticatedUser = Depends(get_current_user),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestReportResponse:
    try:
        data = file.file.read()
        result = service.ingest_report(
            user_id=user.user_id, org_id=org_id, project=project, source=source, data=data
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return IngestReportResponse(**result)


@router.get("/defects", response_model=List[DefectFamilyResponse])
def list_defects_v2(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> List[DefectFamilyResponse]:
    try:
        rows = repo.list_defects(user_id=user.user_id, org_id=org_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [DefectFamilyResponse(**r) for r in rows]


@router.get("/defects/{defect_id}", response_model=DefectLineageResponse)
def defect_lineage_v2(
    defect_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> DefectLineageResponse:
    try:
        data = repo.get_lineage(user_id=user.user_id, defect_id=defect_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    family = DefectFamilySummary(**data["family"]) if data["family"] else None
    return DefectLineageResponse(family=family, failures=[FailureRef(**f) for f in data["failures"]])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_v2_defects.py -v`
Expected: PASS (7).

- [ ] **Step 5: Verify the router mounts in the real app**

Run: `python3 -c "import api; routes=[r.path for r in api.app.routes]; assert '/v2/ingest/report' in routes and '/v2/defects' in routes and '/v2/defects/{defect_id}' in routes, routes; print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/api_v2.py tests/test_api_v2_defects.py
git commit -m "feat: add /v2/ingest/report and /v2/defects endpoints"
```

---

## Task 5: Verificación

- [ ] **Step 1: Unit suite (sin integración)**

Run: `python3 -m pytest -m "not integration" -q`
Expected: PASS (incluye los nuevos modelos/embedder/service/endpoints + todo lo previo).

- [ ] **Step 2: Code review** sobre el diff de las 4 tareas (mapeo de respuestas, manejo de errores 400/403/502, deps perezosas, inmutabilidad con `replace`).

---

## Próximos planes

- **Plan 4:** veredicto de aseguramiento (`src/assurance/report.py`, narrativa LLM async) + `GET /v2/assurance/run/{id}`.
- **Plan 5:** frontend (páginas Assurance + Defect DNA).
- **Plan 6:** documentación (`docs/functional`, `docs/technical`, ADR) + poda legacy + `scripts/seed_demo.py`.
