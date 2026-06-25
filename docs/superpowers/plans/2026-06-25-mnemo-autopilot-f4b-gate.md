# F4b — Gate en CI (check run) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publicar, por run, un check run `mnemo/assurance` (`success`/`failure`/`neutral`) sobre el commit según el veredicto de aseguramiento, reutilizando la política de F4a.

**Architecture:** Extraer `compute_verdict` de `build_certificate` (F4a) para que el cert y el gate compartan la política. Añadir `GitHubCodeHost.publish_check_run` (Checks API). `GateService` orquesta lectura → veredicto → mapeo → publicación. Endpoint `POST /v2/gate/run/{id}`. El check run es saliente (Mnemo→GitHub).

**Tech Stack:** Python 3.13, FastAPI, `requests` (mockeado en tests), pytest.

## Global Constraints

- **Reuso, no duplicación:** la política de veredicto vive en `compute_verdict` (extraída de `build_certificate`); el gate la importa. No reimplementar el if/elif/else.
- **Mapeo fijo:** `_CONCLUSION = {"no-apto": "failure", "apto-con-reservas": "neutral", "apto": "success"}`.
- **Check run:** `name="mnemo/assurance"`, `status="completed"`, `conclusion`, `output={title, summary}`, sobre `head_sha = commit_sha` del run.
- **Determinista, sin LLM.** Funciones puras donde aplique (`compute_verdict`, `_render_output`).
- **Multitenant:** `get_run_meta`/`get_triage_for_run` ya son membership-gated; el repo destino es el del org (config F3c).
- **Errores `/v2`:** 401 sin auth · `ValueError` (run no encontrado / sin `commit_sha` / sin veredictos / GitHub no configurado en el org) → **422** · `GitHubAuthError` → **503** · `GitHubError` → **502** · `psycopg.Error` → **502**.
- **Sin persistencia / sin migración** (el check run vive en GitHub).
- Commits `feat:`/`test:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`. Tests con `python3 -m pytest`.

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `src/certify/certificate.py` | modificar | extraer `compute_verdict`; `build_certificate` lo usa |
| `src/ci/github_app.py` | modificar | `GitHubCodeHost.publish_check_run` |
| `src/certify/gate.py` | crear | `GateService` + `_render_output` + `_CONCLUSION` |
| `src/multitenant_models.py` | modificar | `GateResponse` |
| `src/api_v2.py` | modificar | `get_certificate_repo` (refactor) + `get_gate_service` + endpoint `POST /v2/gate/run/{id}` |
| `tests/test_certify_certificate.py` | modificar | test directo de `compute_verdict` |
| `tests/test_github_app_check_run.py` | crear | `publish_check_run` (`requests` mockeado) |
| `tests/test_certify_gate.py` | crear | `GateService` (mockeado) |
| `tests/test_api_v2_gate.py` | crear | endpoint |

---

## Task 1: Extraer `compute_verdict` (refactor de `certificate.py`)

**Files:**
- Modify: `src/certify/certificate.py`
- Test: `tests/test_certify_certificate.py`

**Interfaces:**
- Produces: `compute_verdict(verdicts: List[Dict[str, Any]]) -> str` (devuelve `"apto"`/`"apto-con-reservas"`/`"no-apto"`). `build_certificate` mantiene su firma y comportamiento (ahora llama a `compute_verdict` para el campo `verdict`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_certify_certificate.py`:

```python
from src.certify.certificate import compute_verdict


def _vv(category, *, rule="", approval=False):
    return {"failure_id": "f", "category": category, "confidence": 0.9,
            "rule_applied": rule, "requires_approval": approval}


def test_compute_verdict_no_apto_on_novel_real():
    assert compute_verdict([_vv("real", rule="R5_real_novel")]) == "no-apto"


def test_compute_verdict_no_apto_on_pending_approval():
    assert compute_verdict([_vv("flaky", approval=True)]) == "no-apto"


def test_compute_verdict_con_reservas_on_recurrent_real_or_maintenance():
    assert compute_verdict([_vv("real", rule="R4_real_recurrent")]) == "apto-con-reservas"
    assert compute_verdict([_vv("maintenance")]) == "apto-con-reservas"


def test_compute_verdict_apto_on_flaky_or_infra():
    assert compute_verdict([_vv("flaky"), _vv("infra")]) == "apto"


def test_compute_verdict_apto_on_empty():
    assert compute_verdict([]) == "apto"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_certify_certificate.py::test_compute_verdict_no_apto_on_novel_real -q` → FAIL (`ImportError`/`AttributeError`).

- [ ] **Step 3: Implement the refactor**

In `src/certify/certificate.py`, add `compute_verdict` above `build_certificate`:

```python
def compute_verdict(verdicts: List[Dict[str, Any]]) -> str:
    """Veredicto de aseguramiento (política §7.1) sobre los veredictos de triaje.
    Compartido por el certificado (F4a) y el gate (F4b)."""
    reales_novel_sin_approval = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") == "R5_real_novel" and not v.get("requires_approval"))
    pendientes_approval = sum(1 for v in verdicts if v.get("requires_approval"))
    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        return "no-apto"
    if any(v.get("category") in ("real", "maintenance") for v in verdicts):
        return "apto-con-reservas"
    return "apto"
```

Then in `build_certificate`, replace the inline verdict block:

```python
    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        verdict = "no-apto"
    elif breakdown["real"] > 0 or breakdown["maintenance"] > 0:
        verdict = "apto-con-reservas"
    else:
        verdict = "apto"
```

with a single call (keep the `reales_novel_sin_approval` / `pendientes_approval` / `reales_recurrentes` / `flaky` lines above — they still feed `risk_score`):

```python
    verdict = compute_verdict(verdicts)
```

- [ ] **Step 4: Run, expect PASS** (new + existing all green)

Run: `python3 -m pytest tests/test_certify_certificate.py -q` → PASS (the 6 existing `build_certificate` tests + the 5 new `compute_verdict` tests).

- [ ] **Step 5: Commit**

```bash
git add src/certify/certificate.py tests/test_certify_certificate.py
git commit -m "refactor(certify): extraer compute_verdict (compartida por cert y gate)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `GitHubCodeHost.publish_check_run`

**Files:**
- Modify: `src/ci/github_app.py`
- Test: `tests/test_github_app_check_run.py`

**Interfaces:**
- Consumes: `GitHubCodeHost` (existing: `_headers`, `_session`, `_repo`, `GitHubError`).
- Produces: `GitHubCodeHost.publish_check_run(*, head_sha: str, conclusion: str, title: str, summary: str) -> str` (devuelve la URL del check run).

- [ ] **Step 1: Write the failing tests** in `tests/test_github_app_check_run.py`:

```python
from unittest.mock import MagicMock

import pytest

from src.ci.github_app import GitHubCodeHost, GitHubError


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        return self._resp


def _codehost(session):
    auth = MagicMock()
    auth.installation_token.return_value = "tok"
    return GitHubCodeHost(auth=auth, installation_id="1", repo_full_name="o/r", session=session)


def test_publish_check_run_posts_completed_and_returns_url():
    session = _Session(_Resp(201, {"html_url": "https://github.com/o/r/runs/1"}))
    url = _codehost(session).publish_check_run(
        head_sha="abc123", conclusion="failure", title="T", summary="S")
    assert url == "https://github.com/o/r/runs/1"
    body = session.calls[0]["json"]
    assert session.calls[0]["url"].endswith("/repos/o/r/check-runs")
    assert body["name"] == "mnemo/assurance"
    assert body["head_sha"] == "abc123"
    assert body["status"] == "completed"
    assert body["conclusion"] == "failure"
    assert body["output"] == {"title": "T", "summary": "S"}


def test_publish_check_run_raises_on_http_error():
    session = _Session(_Resp(422, {}))
    with pytest.raises(GitHubError):
        _codehost(session).publish_check_run(
            head_sha="abc", conclusion="success", title="T", summary="S")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_github_app_check_run.py -q` → FAIL (`AttributeError: publish_check_run`).

- [ ] **Step 3: Implement** — add the method to `GitHubCodeHost` in `src/ci/github_app.py`:

```python
    def publish_check_run(self, *, head_sha: str, conclusion: str,
                          title: str, summary: str) -> str:
        """Publica un check run mnemo/assurance sobre head_sha (Checks API).
        conclusion ∈ {success, failure, neutral}. Devuelve la URL del check run."""
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/check-runs",
            json={"name": "mnemo/assurance", "head_sha": head_sha, "status": "completed",
                  "conclusion": conclusion, "output": {"title": title, "summary": summary}},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"publish check-run falló: HTTP {resp.status_code}")
        return resp.json()["html_url"]
```

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_github_app_check_run.py -q` → PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ci/github_app.py tests/test_github_app_check_run.py
git commit -m "feat(github): GitHubCodeHost.publish_check_run (Checks API)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: `GateService` + endpoint + wiring

**Files:**
- Create: `src/certify/gate.py`
- Modify: `src/multitenant_models.py`, `src/api_v2.py`
- Test: `tests/test_certify_gate.py`, `tests/test_api_v2_gate.py`

**Interfaces:**
- Consumes: `compute_verdict` (Task 1), `GitHubCodeHost.publish_check_run` (Task 2), `AssuranceRepository.get_triage_for_run`, `CertificateRepository.get_run_meta` (returns `{org_id, project, commit_sha}`), `_github_codehost_factory(org_id, user_id)`.
- Produces: `GateService(*, repo, cert_repo, codehost_factory)` with `publish(*, user_id, run_id) -> {verdict, conclusion, check_run_url}`. Endpoint `POST /v2/gate/run/{run_id}`. `get_certificate_repo()`, `get_gate_service()`, `GateResponse`.

- [ ] **Step 1: Implement** `src/certify/gate.py`:

```python
from typing import Any, Callable, Dict, List, Tuple

from src.certify.certificate import compute_verdict

_CONCLUSION = {"no-apto": "failure", "apto-con-reservas": "neutral", "apto": "success"}
_CATEGORIES = ("real", "flaky", "maintenance", "infra", "unknown")
_MOTIVO = {
    "no-apto": "Defecto real novedoso de alta confianza o ítems pendientes de aprobación (Nivel 2).",
    "apto-con-reservas": "Hay defectos reales recurrentes o mantenimiento; revisar antes de liberar.",
    "apto": "Todo flaky en cuarentena, curado o infra reconocida.",
}


def _render_output(verdict: str, verdicts: List[Dict[str, Any]]) -> Tuple[str, str]:
    counts = {c: 0 for c in _CATEGORIES}
    for v in verdicts:
        cat = v.get("category")
        counts[cat if cat in _CATEGORIES else "unknown"] += 1
    desglose = ", ".join(f"{k}: {n}" for k, n in counts.items() if n) or "sin fallos"
    title = f"Mnemo Assurance: {verdict}"
    summary = (f"**Veredicto:** {verdict}\n\n**Desglose:** {desglose}\n\n{_MOTIVO[verdict]}")
    return title, summary


class GateService:
    """Publica el check run mnemo/assurance del run según su veredicto (saliente)."""

    def __init__(self, *, repo, cert_repo, codehost_factory: Callable):
        self.repo = repo                       # AssuranceRepository (get_triage_for_run)
        self.cert_repo = cert_repo             # CertificateRepository (get_run_meta)
        self.codehost_factory = codehost_factory

    def publish(self, *, user_id: str, run_id: str) -> Dict[str, Any]:
        meta = self.cert_repo.get_run_meta(user_id=user_id, run_id=run_id)
        if meta is None:
            raise ValueError("run no encontrado o sin acceso")
        head_sha = meta.get("commit_sha")
        if not head_sha:
            raise ValueError("el run no tiene commit_sha; no se puede publicar el check run")
        verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
        if not verdicts:
            raise ValueError("run sin veredictos de triaje")
        verdict = compute_verdict(verdicts)
        conclusion = _CONCLUSION[verdict]
        title, summary = _render_output(verdict, verdicts)
        codehost = self.codehost_factory(meta["org_id"], user_id)
        url = codehost.publish_check_run(head_sha=head_sha, conclusion=conclusion,
                                         title=title, summary=summary)
        return {"verdict": verdict, "conclusion": conclusion, "check_run_url": url}
```

- [ ] **Step 2: Write the failing `GateService` tests** in `tests/test_certify_gate.py`:

```python
from unittest.mock import MagicMock

import pytest

from src.certify.gate import GateService


def _service(*, meta, verdicts, codehost=None):
    repo = MagicMock()
    repo.get_triage_for_run.return_value = verdicts
    cert_repo = MagicMock()
    cert_repo.get_run_meta.return_value = meta
    codehost = codehost or MagicMock()
    codehost.publish_check_run.return_value = "https://github.com/o/r/runs/1"
    factory = MagicMock(return_value=codehost)
    svc = GateService(repo=repo, cert_repo=cert_repo, codehost_factory=factory)
    return svc, codehost, factory


_META = {"org_id": "o1", "project": "web", "commit_sha": "sha9"}


def _v(category, *, rule="", approval=False):
    return {"failure_id": "f", "category": category, "rule_applied": rule,
            "requires_approval": approval, "confidence": 0.9}


def test_publish_failure_for_novel_real():
    svc, codehost, _ = _service(meta=_META, verdicts=[_v("real", rule="R5_real_novel")])
    out = svc.publish(user_id="u", run_id="r")
    assert out["verdict"] == "no-apto" and out["conclusion"] == "failure"
    assert out["check_run_url"] == "https://github.com/o/r/runs/1"
    kwargs = codehost.publish_check_run.call_args.kwargs
    assert kwargs["head_sha"] == "sha9" and kwargs["conclusion"] == "failure"


def test_publish_neutral_for_recurrent_real():
    svc, _, _ = _service(meta=_META, verdicts=[_v("real", rule="R4_real_recurrent")])
    assert svc.publish(user_id="u", run_id="r")["conclusion"] == "neutral"


def test_publish_success_for_flaky():
    svc, _, _ = _service(meta=_META, verdicts=[_v("flaky")])
    assert svc.publish(user_id="u", run_id="r")["conclusion"] == "success"


def test_publish_raises_without_commit_sha():
    svc, _, _ = _service(meta={"org_id": "o1", "project": "web", "commit_sha": None},
                         verdicts=[_v("flaky")])
    with pytest.raises(ValueError):
        svc.publish(user_id="u", run_id="r")


def test_publish_raises_without_verdicts():
    svc, _, _ = _service(meta=_META, verdicts=[])
    with pytest.raises(ValueError):
        svc.publish(user_id="u", run_id="r")


def test_publish_raises_when_run_not_found():
    svc, _, _ = _service(meta=None, verdicts=[_v("flaky")])
    with pytest.raises(ValueError):
        svc.publish(user_id="u", run_id="r")
```

- [ ] **Step 3: Run, expect PASS** (gate.py already implemented in Step 1)

Run: `python3 -m pytest tests/test_certify_gate.py -q` → PASS (6 passed).

- [ ] **Step 4: Models** — add to `src/multitenant_models.py` (near the others):

```python
class GateResponse(BaseModel):
    verdict: str
    conclusion: str
    check_run_url: str
```

- [ ] **Step 5: Wire `api_v2.py`**.

Imports: add `GateService` and `GateResponse`:

```python
from src.certify.gate import GateService
```
and add `GateResponse` to the `from src.multitenant_models import (...)` block. (`GitHubError`, `GitHubAuthError`, `psycopg`, `CertificateRepository` are already imported.)

Add the `_gate_service` global next to `_certificate_service`:

```python
_gate_service = None
```

Refactor `get_certificate_service` to share the repo, and add `get_certificate_repo` + `get_gate_service`. Replace the current `get_certificate_service` body:

```python
def get_certificate_repo() -> CertificateRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _cert_repo
    if _cert_repo is None:
        _cert_repo = CertificateRepository()
    return _cert_repo


def get_certificate_service() -> CertificateService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _certificate_service
    if _certificate_service is None:
        _certificate_service = CertificateService(
            repo=get_assurance_repo(), cert_repo=get_certificate_repo(),
            private_key=MNEMO_SIGNING_PRIVATE_KEY, public_key=MNEMO_SIGNING_PUBLIC_KEY,
            mnemo_version=MNEMO_VERSION, model_version=LLM_MODEL or "unknown",
        )
    return _certificate_service


def get_gate_service() -> GateService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _gate_service
    if _gate_service is None:
        _gate_service = GateService(repo=get_assurance_repo(), cert_repo=get_certificate_repo(),
                                    codehost_factory=_github_codehost_factory)
    return _gate_service
```

Add the endpoint (near the certificate endpoints):

```python
@router.post("/gate/run/{run_id}", response_model=GateResponse)
def publish_gate_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: GateService = Depends(get_gate_service),
) -> GateResponse:
    try:
        return GateResponse(**service.publish(user_id=user.user_id, run_id=run_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=503, detail="GitHub App no configurada") from exc
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail="GitHub API error") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
```

- [ ] **Step 6: Write the failing endpoint tests** in `tests/test_api_v2_gate.py`:

```python
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.ci.github_app import GitHubError
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if service is not None:
        app.dependency_overrides[api_v2.get_gate_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_publish_gate_returns_conclusion():
    svc = MagicMock()
    svc.publish.return_value = {"verdict": "no-apto", "conclusion": "failure",
                               "check_run_url": "https://github.com/o/r/runs/1"}
    resp = _client(service=svc).post("/v2/gate/run/r1")
    assert resp.status_code == 200
    assert resp.json()["conclusion"] == "failure"


def test_publish_gate_value_error_is_422():
    svc = MagicMock()
    svc.publish.side_effect = ValueError("run sin veredictos de triaje")
    assert _client(service=svc).post("/v2/gate/run/r1").status_code == 422


def test_publish_gate_github_error_is_502():
    svc = MagicMock()
    svc.publish.side_effect = GitHubError("boom")
    assert _client(service=svc).post("/v2/gate/run/r1").status_code == 502


def test_publish_gate_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/gate/run/r1").status_code == 401
```

- [ ] **Step 7: Run, expect PASS**

Run: `python3 -m pytest tests/test_api_v2_gate.py -q` → PASS (4 passed).

- [ ] **Step 8: Full suite + commit**

Run: `python3 -m pytest -m "not integration" -q` → green. Then:

```bash
git add src/certify/gate.py src/multitenant_models.py src/api_v2.py tests/test_certify_gate.py tests/test_api_v2_gate.py
git commit -m "feat(certify): GateService + endpoint POST /v2/gate/run/{id} (check run mnemo/assurance)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Despliegue:** la GitHub App necesita el permiso **Checks: write** (además de los de F3c). El repo destino sale de la config GitHub del org (F3c).
- **Diferencia con el spec:** el `ValueError` de `_github_codehost_factory` (GitHub no configurado en el org) se mapea a **422** junto con los demás `ValueError` (el spec mencionaba 400; se unifica a 422 para no introspeccionar el mensaje de la excepción).
- **Idempotencia / re-disparo:** re-llamar el endpoint tras aprobar el self-heal publica un nuevo check run con la nueva conclusión (GitHub muestra el más reciente del mismo `name`). Sin estado local.
- **Fuera de alcance:** disparo automático en el webhook CI; persistir histórico de gates; status `in_progress`.
