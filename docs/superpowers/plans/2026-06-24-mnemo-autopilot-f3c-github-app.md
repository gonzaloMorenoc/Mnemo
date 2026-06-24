# F3c — GitHub App + materialización real de Issues — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Al aprobar una acción, materializar un Issue real de GitHub (ticket de defecto / cuarentena con deuda) mediante una GitHub App, de forma segura (sin huérfanos ni duplicados) y aislada por org.

**Architecture:** GitHub App global (credenciales en env) + `installation_id`/`repo_full_name` por-org en `org_integrations`. Auth JWT RS256 (`pyjwt`) → installation token efímero (cache) → API REST con `requests`. Materialización con estados `proposed → approved → materialized` y marcador idempotente en el body del Issue. Se extrae `ActionRepository` de `AssuranceRepository`.

**Tech Stack:** Python 3.13, FastAPI, psycopg (dict_row), `pyjwt`, `requests`, `cryptography` (ya en `requirements.txt`); pytest (+ `@pytest.mark.integration` para Postgres).

## Global Constraints

- **Aislamiento multitenant en la capa de app:** el pooler hace BYPASS de RLS → cada método de repo valida membership con `exists(select 1 from public.memberships where org_id=%s and user_id=%s)`. Nunca quitar estos filtros.
- **Inmutabilidad:** value objects con `@dataclass(frozen=True)`; no mutar dicts compartidos.
- **Errores `/v2`:** auth 401 · no-miembro → `PermissionError`→403 (o vacío en lecturas) · validación/datos malos → `ValueError`→400 · multi-tenant no configurado 503 · BD `psycopg.Error`→502.
- **SQL siempre parametrizado** (`%s`), nunca f-strings con input de usuario.
- **Nivel 2 estricto:** nada se materializa sin un `approve` válido (solo una acción que pasó de `proposed`→`approved`).
- **Cliente HTTP = `requests`** (el repo no usa httpx). Timeouts explícitos (15 s).
- **Archivos pequeños** (<400 líneas), funciones <50 líneas.
- **Commits:** uno por tarea, formato `feat:`/`fix:`/`refactor:`/`test:`, terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.
- Tests sin GitHub real: `requests` se inyecta como `session` y se mockea. Postgres solo en tests marcados `integration`.
- Ejecutar la suite con `python3 -m pytest` (no `python`).

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `db/migrations/011_github_integration.sql` | crear | columnas github en `org_integrations` + FK `actions.approved_by` |
| `src/config.py` | modificar | `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` |
| `src/multitenant_models.py` | modificar | `GitHubConfigRequest/Response`; `ActionApproveResponse.materialized`; `ActionResponse.org_id` |
| `src/jira/integrations_repository.py` | modificar | `upsert_github_config` / `get_github_config` |
| `src/ci/github_auth.py` | crear | `GitHubAppAuth` (JWT + installation token + cache) + `GitHubAuthError` |
| `src/ci/github_app.py` | crear | `GitHubCodeHost` (create_issue idempotente) + `GitHubError` |
| `src/actions/repository.py` | crear | `ActionRepository` (CRUD + `approve_action`/`materialize_action`) |
| `src/defects/repository.py` | modificar | quitar el CRUD de acciones (se mueve); conservar lecturas de contexto |
| `src/actions/base.py` | modificar | `CodeHost.create_issue(..., marker)`; `NullCodeHost` |
| `src/actions/service.py` | modificar | `actions_repo` + `codehost_factory` + flujo `approve→materialize` |
| `src/api_v2.py` | modificar | endpoints `/v2/integrations/github`; `get_action_repo`; factory real; whitelist status |
| `tests/test_github_auth.py` | crear | tests de `GitHubAppAuth` |
| `tests/test_github_app.py` | crear | tests de `GitHubCodeHost` |
| `tests/test_actions_repository.py` | modificar | usar `ActionRepository`; flujo approve/materialize |
| `tests/test_actions_service.py` | modificar | `codehost_factory`; idempotencia; self_heal |
| `tests/test_api_v2_actions.py` | modificar | integración github; approve materializa; status inválido |
| `tests/test_integrations_repository.py` | modificar | github upsert/get (integration) |

---

## Task 1: Migración 011 + config GitHub por-org + endpoints

**Files:**
- Create: `db/migrations/011_github_integration.sql`
- Modify: `src/config.py`, `src/multitenant_models.py`, `src/jira/integrations_repository.py`, `src/api_v2.py`
- Test: `tests/test_integrations_repository.py`, `tests/test_api_v2_actions.py`

**Interfaces:**
- Produces: `IntegrationsRepository.upsert_github_config(*, user_id, org_id, installation_id, repo_full_name) -> None`; `get_github_config(*, user_id, org_id) -> Dict` con `{configured: bool, repo_full_name: Optional[str], installation_id: Optional[str]}`. Modelos `GitHubConfigRequest{org_id, installation_id, repo_full_name}`, `GitHubConfigResponse{configured, repo_full_name?, installation_id?}`. Env `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`.

- [ ] **Step 1: Escribir la migración**

Create `db/migrations/011_github_integration.sql`:

```sql
-- db/migrations/011_github_integration.sql
-- F3c: integración GitHub App por-org (installation + repo destino) sobre org_integrations.
-- Además: FK de auditoría que faltaba en actions.approved_by (revisión de F3a).

alter table public.org_integrations drop constraint if exists org_integrations_provider_check;
alter table public.org_integrations add constraint org_integrations_provider_check
    check (provider in ('jira', 'github'));

alter table public.org_integrations add column if not exists installation_id text;
alter table public.org_integrations add column if not exists repo_full_name text;

-- github no usa estas columnas (la private key es global, en env) → nullable
alter table public.org_integrations alter column email drop not null;
alter table public.org_integrations alter column api_token_enc drop not null;
alter table public.org_integrations alter column jql drop not null;

alter table public.actions drop constraint if exists actions_approved_by_fkey;
alter table public.actions add constraint actions_approved_by_fkey
    foreign key (approved_by) references auth.users (id) on delete set null;
```

- [ ] **Step 2: Añadir las env vars** en `src/config.py` (junto a las otras `os.getenv`):

```python
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY", "")
```

- [ ] **Step 3: Añadir los modelos** en `src/multitenant_models.py` (junto a los de Jira):

```python
class GitHubConfigRequest(BaseModel):
    org_id: str
    installation_id: str
    repo_full_name: str


class GitHubConfigResponse(BaseModel):
    configured: bool
    repo_full_name: Optional[str] = None
    installation_id: Optional[str] = None
```

- [ ] **Step 4: Escribir el test de integración del repo** en `tests/test_integrations_repository.py` (añadir):

```python
def test_github_upsert_then_get(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.upsert_github_config(user_id=u, org_id=o, installation_id="42", repo_full_name="acme/web")
    cfg = repo.get_github_config(user_id=u, org_id=o)
    assert cfg == {"configured": True, "repo_full_name": "acme/web", "installation_id": "42"}


def test_github_get_unconfigured(repo, org):
    cfg = repo.get_github_config(user_id=org["user_id"], org_id=org["org_id"])
    assert cfg == {"configured": False, "repo_full_name": None, "installation_id": None}


def test_github_upsert_non_member_rejected(repo, org):
    import uuid as _u
    with pytest.raises(PermissionError):
        repo.upsert_github_config(user_id=str(_u.uuid4()), org_id=org["org_id"],
                                  installation_id="1", repo_full_name="x/y")
```

- [ ] **Step 5: Run integration tests, expect FAIL**

Run: `python3 -m pytest tests/test_integrations_repository.py -q -k github`
Expected: FAIL (`AttributeError: ... upsert_github_config`).

- [ ] **Step 6: Implementar los métodos** en `src/jira/integrations_repository.py` (añadir al final de la clase):

```python
    def upsert_github_config(self, *, user_id: str, org_id: str,
                             installation_id: str, repo_full_name: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    """
                    insert into public.org_integrations
                        (org_id, provider, base_url, installation_id, repo_full_name)
                    values (%s, 'github', 'https://github.com', %s, %s)
                    on conflict (org_id, provider) do update
                       set installation_id = excluded.installation_id,
                           repo_full_name = excluded.repo_full_name,
                           updated_at = now()
                    """,
                    (org_id, installation_id, repo_full_name),
                )
            conn.commit()

    def get_github_config(self, *, user_id: str, org_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._require_member(cur, org_id, user_id)
                cur.execute(
                    "select installation_id, repo_full_name from public.org_integrations"
                    " where org_id = %s and provider = 'github'",
                    (org_id,),
                )
                row = cur.fetchone()
        if row is None:
            return {"configured": False, "repo_full_name": None, "installation_id": None}
        return {"configured": True, "repo_full_name": row["repo_full_name"],
                "installation_id": row["installation_id"]}
```

- [ ] **Step 7: Run integration tests, expect PASS**

Run: `python3 -m pytest tests/test_integrations_repository.py -q -k github`
Expected: PASS (requiere `DATABASE_URL` + migración 011 aplicada; si no, los tests se `skip`).

- [ ] **Step 8: Escribir el test de endpoint** en `tests/test_api_v2_actions.py` (añadir; `_client` ya existe pero no overridea `get_integrations_repo` — añadir soporte):

Primero, extender el helper `_client` para aceptar `integrations`:

```python
def _client(*, repo=None, service=None, integrations=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if service is not None:
        app.dependency_overrides[api_v2.get_action_service] = lambda: service
    if integrations is not None:
        app.dependency_overrides[api_v2.get_integrations_repo] = lambda: integrations
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)
```

Luego los tests:

```python
def test_set_github_integration():
    integ = MagicMock()
    resp = _client(integrations=integ).post(
        "/v2/integrations/github",
        json={"org_id": "o1", "installation_id": "42", "repo_full_name": "acme/web"})
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "repo_full_name": "acme/web", "installation_id": "42"}
    integ.upsert_github_config.assert_called_once_with(
        user_id="user-1", org_id="o1", installation_id="42", repo_full_name="acme/web")


def test_get_github_integration():
    integ = MagicMock()
    integ.get_github_config.return_value = {"configured": True, "repo_full_name": "acme/web",
                                            "installation_id": "42"}
    resp = _client(integrations=integ).get("/v2/integrations/github?org_id=o1")
    assert resp.status_code == 200 and resp.json()["repo_full_name"] == "acme/web"


def test_set_github_integration_non_member_403():
    integ = MagicMock()
    integ.upsert_github_config.side_effect = PermissionError("nope")
    resp = _client(integrations=integ).post(
        "/v2/integrations/github",
        json={"org_id": "o1", "installation_id": "42", "repo_full_name": "acme/web"})
    assert resp.status_code == 403


def test_set_github_integration_requires_auth():
    assert _client(integrations=MagicMock(), with_user=False).post(
        "/v2/integrations/github",
        json={"org_id": "o", "installation_id": "1", "repo_full_name": "a/b"}).status_code == 401
```

- [ ] **Step 9: Run endpoint tests, expect FAIL**

Run: `python3 -m pytest tests/test_api_v2_actions.py -q -k github`
Expected: FAIL (404 — endpoints no existen).

- [ ] **Step 10: Implementar los endpoints** en `src/api_v2.py`. Añadir los imports de modelos (`GitHubConfigRequest`, `GitHubConfigResponse`) al bloque `from src.multitenant_models import (...)`, y añadir los endpoints (junto a los de Jira):

```python
@router.post("/integrations/github", response_model=GitHubConfigResponse)
def set_github_integration(
    body: GitHubConfigRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> GitHubConfigResponse:
    try:
        integrations.upsert_github_config(
            user_id=user.user_id, org_id=body.org_id,
            installation_id=body.installation_id, repo_full_name=body.repo_full_name,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return GitHubConfigResponse(configured=True, repo_full_name=body.repo_full_name,
                                installation_id=body.installation_id)


@router.get("/integrations/github", response_model=GitHubConfigResponse)
def get_github_integration(
    org_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    integrations: IntegrationsRepository = Depends(get_integrations_repo),
) -> GitHubConfigResponse:
    try:
        cfg = integrations.get_github_config(user_id=user.user_id, org_id=org_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return GitHubConfigResponse(**cfg)
```

- [ ] **Step 11: Run endpoint tests, expect PASS**

Run: `python3 -m pytest tests/test_api_v2_actions.py -q -k github`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add db/migrations/011_github_integration.sql src/config.py src/multitenant_models.py \
        src/jira/integrations_repository.py src/api_v2.py \
        tests/test_integrations_repository.py tests/test_api_v2_actions.py
git commit -m "feat(github): config GitHub App por-org (migración 011 + endpoints /v2/integrations/github)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `GitHubAppAuth` (JWT + installation token + cache)

**Files:**
- Create: `src/ci/github_auth.py`
- Test: `tests/test_github_auth.py`

**Interfaces:**
- Consumes: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` (config).
- Produces: `GitHubAuthError(RuntimeError)`; `GitHubAppAuth(*, app_id=GITHUB_APP_ID, private_key=GITHUB_APP_PRIVATE_KEY, session=requests)` con `app_jwt() -> str` y `installation_token(installation_id: str) -> str` (cacheado).

- [ ] **Step 1: Escribir los tests** en `tests/test_github_auth.py`:

```python
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.ci.github_auth import GitHubAppAuth, GitHubAuthError


@pytest.fixture(scope="module")
def private_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def test_app_jwt_has_iss_and_exp(private_key):
    tok = GitHubAppAuth(app_id="123", private_key=private_key).app_jwt()
    decoded = jwt.decode(tok, options={"verify_signature": False})
    assert decoded["iss"] == "123" and decoded["exp"] > decoded["iat"]


def test_app_jwt_missing_config_raises():
    with pytest.raises(GitHubAuthError):
        GitHubAppAuth(app_id="", private_key="").app_jwt()


def test_installation_token_caches(private_key):
    calls = []

    class _Resp:
        status_code = 201
        def json(self):
            return {"token": "ghs_abc", "expires_at": "2999-01-01T00:00:00Z"}

    class _Sess:
        def post(self, *a, **k):
            calls.append(1)
            return _Resp()

    auth = GitHubAppAuth(app_id="1", private_key=private_key, session=_Sess())
    assert auth.installation_token("99") == "ghs_abc"
    assert auth.installation_token("99") == "ghs_abc"  # 2ª vez = cache
    assert len(calls) == 1


def test_installation_token_error_raises(private_key):
    class _Resp:
        status_code = 404
        def json(self):
            return {}

    class _Sess:
        def post(self, *a, **k):
            return _Resp()

    auth = GitHubAppAuth(app_id="1", private_key=private_key, session=_Sess())
    with pytest.raises(GitHubAuthError):
        auth.installation_token("99")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_github_auth.py -q`
Expected: FAIL (`ModuleNotFoundError: src.ci.github_auth`).

- [ ] **Step 3: Implementar** `src/ci/github_auth.py`:

```python
import time
from datetime import datetime
from typing import Dict, Optional, Tuple

import jwt
import requests

from src.config import GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY

_API = "https://api.github.com"


class GitHubAuthError(RuntimeError):
    """Credenciales de la GitHub App ausentes/ inválidas o fallo al pedir el token."""


def _parse_expiry(value: Optional[str]) -> float:
    if not value:
        return time.time() + 3000.0
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class GitHubAppAuth:
    """Autenticación de la GitHub App: JWT firmado con la private key (env) →
    installation access token efímero, cacheado por installation_id."""

    def __init__(self, *, app_id: str = GITHUB_APP_ID,
                 private_key: str = GITHUB_APP_PRIVATE_KEY,
                 session: Optional[object] = None):
        self._app_id = app_id
        self._private_key = private_key
        self._session = session or requests
        self._cache: Dict[str, Tuple[str, float]] = {}

    def app_jwt(self) -> str:
        if not self._app_id or not self._private_key:
            raise GitHubAuthError("GitHub App no configurada (GITHUB_APP_ID/PRIVATE_KEY)")
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": self._app_id}  # exp ≤ 10 min
        try:
            return jwt.encode(payload, self._private_key, algorithm="RS256")
        except Exception as exc:  # clave malformada
            raise GitHubAuthError("private key de la GitHub App inválida") from exc

    def installation_token(self, installation_id: str) -> str:
        cached = self._cache.get(installation_id)
        if cached and cached[1] - time.time() > 300:
            return cached[0]
        resp = self._session.post(
            f"{_API}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self.app_jwt()}",
                     "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubAuthError(f"installation token falló: HTTP {resp.status_code}")
        data = resp.json()
        token = data["token"]
        self._cache[installation_id] = (token, _parse_expiry(data.get("expires_at")))
        return token
```

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_github_auth.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ci/github_auth.py tests/test_github_auth.py
git commit -m "feat(github): GitHubAppAuth (JWT RS256 + installation token cacheado)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: `GitHubCodeHost` (create_issue idempotente)

**Files:**
- Create: `src/ci/github_app.py`
- Test: `tests/test_github_app.py`

**Interfaces:**
- Consumes: `GitHubAppAuth.installation_token(id)`.
- Produces: `GitHubError(RuntimeError)`; `GitHubCodeHost(*, auth, installation_id, repo_full_name, session=requests)` con `create_issue(*, title, body, labels, marker="") -> str` (devuelve `html_url`; si `marker` ya existe en un Issue → reusa) y `open_draft_pr(...) -> str` (`NotImplementedError`).

- [ ] **Step 1: Escribir los tests** en `tests/test_github_app.py`:

```python
from unittest.mock import MagicMock

import pytest

from src.ci.github_app import GitHubCodeHost, GitHubError


def _auth():
    a = MagicMock()
    a.installation_token.return_value = "ghs_tok"
    return a


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def test_create_issue_posts_and_returns_url():
    posted = {}

    class _Sess:
        def get(self, *a, **k):
            return _Resp(200, {"items": []})  # search vacío

        def post(self, url, json=None, headers=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            return _Resp(201, {"html_url": "https://github.com/o/r/issues/1"})

    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=_Sess())
    url = ch.create_issue(title="T", body="B", labels=["bug"], marker="mnemo:action:a1")
    assert url == "https://github.com/o/r/issues/1"
    assert posted["url"].endswith("/repos/o/r/issues")
    assert "<!-- mnemo:action:a1 -->" in posted["json"]["body"]  # marcador anexado
    assert posted["json"]["labels"] == ["bug"]


def test_create_issue_reuses_when_marker_found():
    class _Sess:
        def get(self, *a, **k):
            return _Resp(200, {"items": [{"html_url": "https://github.com/o/r/issues/5"}]})

        def post(self, *a, **k):
            raise AssertionError("no debe crear si el marcador ya existe")

    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=_Sess())
    assert ch.create_issue(title="T", body="B", labels=[], marker="mnemo:action:a1") \
        == "https://github.com/o/r/issues/5"


def test_create_issue_raises_on_api_error():
    class _Sess:
        def get(self, *a, **k):
            return _Resp(200, {"items": []})

        def post(self, *a, **k):
            return _Resp(422, {})

    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=_Sess())
    with pytest.raises(GitHubError):
        ch.create_issue(title="T", body="B", labels=[], marker="m")


def test_open_draft_pr_not_implemented():
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name="o/r", session=MagicMock())
    with pytest.raises(NotImplementedError):
        ch.open_draft_pr(title="t", body="b", patch="p")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_github_app.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implementar** `src/ci/github_app.py`:

```python
from typing import List, Optional

import requests

from src.ci.github_auth import GitHubAppAuth

_API = "https://api.github.com"


class GitHubError(RuntimeError):
    """Fallo de la API REST de GitHub al materializar un artefacto."""


class GitHubCodeHost:
    """CodeHost real: crea Issues en el repo del org. Idempotente por marcador oculto
    en el body (no duplica al reintentar). open_draft_pr llega en F3c-2."""

    def __init__(self, *, auth: GitHubAppAuth, installation_id: str,
                 repo_full_name: str, session: Optional[object] = None):
        self._auth = auth
        self._installation_id = installation_id
        self._repo = repo_full_name
        self._session = session or requests

    def _headers(self) -> dict:
        token = self._auth.installation_token(self._installation_id)
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def _find_by_marker(self, marker: str) -> Optional[str]:
        resp = self._session.get(
            f"{_API}/search/issues",
            params={"q": f'repo:{self._repo} in:body "{marker}"'},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            return None  # búsqueda no disponible → seguimos a crear
        items = resp.json().get("items", [])
        return items[0]["html_url"] if items else None

    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str:
        if marker:
            existing = self._find_by_marker(marker)
            if existing:
                return existing
            body = f"{body}\n\n<!-- {marker} -->"
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/issues",
            json={"title": title, "body": body, "labels": labels},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"crear issue falló: HTTP {resp.status_code}")
        return resp.json()["html_url"]

    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str:
        raise NotImplementedError("open_draft_pr (self-heal → PR) es F3c-2")
```

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_github_app.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ci/github_app.py tests/test_github_app.py
git commit -m "feat(github): GitHubCodeHost.create_issue idempotente (marcador oculto en el body)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 4: Extraer `ActionRepository` (CRUD + approve/materialize divididos)

**Files:**
- Create: `src/actions/repository.py`
- Modify: `src/defects/repository.py` (quitar el CRUD de acciones; conservar `get_run_actionable_verdicts`, `get_family_with_failures`, `get_selfheal_context`)
- Test: `tests/test_actions_repository.py`

**Interfaces:**
- Produces: `ActionRepository(db_url=DATABASE_URL)` con `save_actions(*, user_id, org_id, run_id, actions) -> int`, `get_actions(*, user_id, org_id, status=None) -> List[Dict]`, `get_action(*, user_id, action_id) -> Optional[Dict]` (incluye `org_id`), `approve_action(*, user_id, action_id) -> bool` (`proposed→approved`), `materialize_action(*, user_id, action_id, artifact_ref) -> bool` (`approved→materialized`), `reject_action(*, user_id, action_id, reason) -> bool`. Cada dict de acción tiene: `id, triage_verdict_id, run_id, org_id, kind, payload, summary, status, artifact_ref, approved_by, approved_at, reject_reason`.

- [ ] **Step 1: Crear `ActionRepository`** en `src/actions/repository.py` (mueve el CRUD desde `defects/repository.py`, dividiendo `approve_action` y añadiendo `org_id` a `get_action`/`_action_rows`):

```python
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.config import DATABASE_URL


class ActionRepository:
    """Acceso a datos de la capa de acción (tabla public.actions). El pooler hace
    BYPASS de RLS → cada método valida membership en la capa de app."""

    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.db_url, row_factory=dict_row)

    def _set_claims(self, conn: psycopg.Connection, user_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def _rows(self, cur) -> List[Dict[str, Any]]:
        return [
            {"id": str(r["id"]), "triage_verdict_id": str(r["triage_verdict_id"]),
             "run_id": str(r["run_id"]), "org_id": str(r["org_id"]), "kind": r["kind"],
             "payload": r["payload"], "summary": r["summary"], "status": r["status"],
             "artifact_ref": r["artifact_ref"],
             "approved_by": str(r["approved_by"]) if r["approved_by"] else None,
             "approved_at": r["approved_at"].isoformat() if r["approved_at"] else None,
             "reject_reason": r["reject_reason"]}
            for r in cur.fetchall()
        ]

    def save_actions(self, *, user_id: str, org_id: str, run_id: str,
                     actions: List[Dict[str, Any]]) -> int:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute("select 1 from public.test_runs where id = %s and org_id = %s",
                            (run_id, org_id))
                if cur.fetchone() is None:
                    raise ValueError("run does not belong to the organization")
                cur.execute("delete from public.actions where run_id = %s and status = 'proposed'",
                            (run_id,))
                for a in actions:
                    cur.execute(
                        "insert into public.actions"
                        " (triage_verdict_id, run_id, org_id, kind, payload, summary)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (a["triage_verdict_id"], run_id, org_id, a["kind"],
                         Json(a.get("payload")), a.get("summary")),
                    )
            conn.commit()
        return len(actions)

    _COLS = ("id, triage_verdict_id, run_id, org_id, kind, payload, summary, status,"
             " artifact_ref, approved_by, approved_at, reject_reason")

    def get_actions(self, *, user_id: str, org_id: str,
                    status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return []
                if status:
                    cur.execute(f"select {self._COLS} from public.actions"
                                " where org_id = %s and status = %s order by created_at desc",
                                (org_id, status))
                else:
                    cur.execute(f"select {self._COLS} from public.actions"
                                " where org_id = %s order by created_at desc", (org_id,))
                return self._rows(cur)

    def get_action(self, *, user_id: str, action_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    f"select {self._COLS} from public.actions a"
                    " where a.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = a.org_id and m.user_id = %s)",
                    (action_id, user_id),
                )
                rows = self._rows(cur)
                return rows[0] if rows else None

    def approve_action(self, *, user_id: str, action_id: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'approved',"
                    "  approved_by = %s, approved_at = now()"
                    " where a.id = %s and a.status = 'proposed'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
                    (user_id, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def materialize_action(self, *, user_id: str, action_id: str, artifact_ref: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'materialized', artifact_ref = %s"
                    " where a.id = %s and a.status = 'approved'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
                    (artifact_ref, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def reject_action(self, *, user_id: str, action_id: str, reason: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'rejected', reject_reason = %s"
                    " where a.id = %s and a.status = 'proposed'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
                    (reason, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok
```

- [ ] **Step 2: Borrar de `src/defects/repository.py`** los métodos movidos: `save_actions`, `_action_rows`, `get_actions`, `get_action`, `approve_action`, `reject_action`. **Conservar** `get_run_actionable_verdicts`, `get_family_with_failures`, `get_selfheal_context`. (El `approve_action` antiguo tomaba `artifact_ref`; ya no existe aquí.)

- [ ] **Step 3: Actualizar el test de integración** en `tests/test_actions_repository.py`. Añadir el import y un fixture `arepo`, y reescribir el roundtrip al nuevo flujo:

```python
from src.actions.repository import ActionRepository
from src.defects.repository import AssuranceRepository, IngestItem


@pytest.fixture
def arepo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return ActionRepository(DBURL)
```

Reemplazar `test_save_get_approve_reject_roundtrip` por:

```python
def test_save_approve_materialize_roundtrip(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    assert arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {"title": "T"}, "summary": "s"}]) == 1
    inbox = arepo.get_actions(user_id=u, org_id=o, status="proposed")
    assert len(inbox) == 1
    aid = inbox[0]["id"]
    # proposed → approved (sin ref)
    assert arepo.approve_action(user_id=u, action_id=aid) is True
    got = arepo.get_actions(user_id=u, org_id=o)[0]
    assert got["status"] == "approved" and got["approved_by"] == u and got["artifact_ref"] is None
    # approved → materialized (con ref)
    assert arepo.materialize_action(user_id=u, action_id=aid,
                                    artifact_ref="https://github.com/o/r/issues/1") is True
    got = arepo.get_actions(user_id=u, org_id=o)[0]
    assert got["status"] == "materialized" and got["artifact_ref"] == "https://github.com/o/r/issues/1"
    # materializar de nuevo → False (ya no está 'approved')
    assert arepo.materialize_action(user_id=u, action_id=aid, artifact_ref="x") is False


def test_get_action_includes_org_id(repo, arepo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    arepo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s"}])
    aid = arepo.get_actions(user_id=u, org_id=o)[0]["id"]
    assert arepo.get_action(user_id=u, action_id=aid)["org_id"] == o
```

En `test_save_actions_preserves_approved_on_reproposal` y `test_save_actions_rejects_foreign_run`, sustituir `repo.save_actions`/`repo.approve_action`/`repo.get_actions` por `arepo.*`, y `arepo.approve_action(user_id=u, action_id=aid)` (sin `artifact_ref`). `get_run_actionable_verdicts` y `get_selfheal_context` siguen en `repo` (AssuranceRepository).

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_actions_repository.py -q`
Expected: PASS (o `skip` sin `DATABASE_URL`).

- [ ] **Step 5: Verificar que nada más use los métodos movidos**

Run: `grep -rn "\.approve_action(\|\.get_action(\|\.save_actions(\|\.reject_action(\|\.get_actions(" src/ | grep -v "src/actions/repository.py"`
Expected: solo apariciones en `src/actions/service.py` y `src/api_v2.py` (se arreglan en Tasks 5–6).

- [ ] **Step 6: Commit**

```bash
git add src/actions/repository.py src/defects/repository.py tests/test_actions_repository.py
git commit -m "refactor(actions): extraer ActionRepository; dividir approve/materialize; get_action con org_id

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 5: `ActionService` con `codehost_factory` + flujo approve→materialize

**Files:**
- Modify: `src/actions/base.py` (firma `create_issue` con `marker`), `src/actions/service.py`
- Test: `tests/test_actions_service.py`

**Interfaces:**
- Consumes: `ActionRepository` (Task 4), `CodeHost.create_issue(*, title, body, labels, marker)`.
- Produces: `ActionService(*, repo, actuators, actions_repo=None, codehost_factory=None)` (si `actions_repo` es None → usa `repo`; si `codehost_factory` es None → `NullCodeHost`). `codehost_factory: Callable[[org_id, user_id], CodeHost]`. `approve_action` devuelve `{"approved": bool, "materialized": bool, "artifact_ref": Optional[str]}`.

- [ ] **Step 1: Actualizar `CodeHost`/`NullCodeHost`** en `src/actions/base.py`:

```python
class CodeHost(Protocol):
    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str: ...
    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str: ...


class NullCodeHost:
    """Stub: NO escribe en ningún sitio externo (default de tests / sin GitHub)."""

    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str:
        return "stub://issue/pending"

    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str:
        return "stub://pr/pending"
```

- [ ] **Step 2: Reescribir los tests de approve** en `tests/test_actions_service.py` (reemplazar `test_approve_materializes_via_codehost_and_records_ref`, `test_approve_quarantine_materializes_debt_ticket` y `test_approve_non_proposed_does_not_materialize`):

```python
def test_approve_materializes_via_codehost_and_records_ref():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "org_id": "o", "kind": "ticket", "status": "proposed",
                                    "payload": {"title": "T", "body": "B", "labels": ["bug"]}}
    repo.approve_action.return_value = True
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "https://github.com/o/r/issues/9"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "materialized": True,
                   "artifact_ref": "https://github.com/o/r/issues/9"}
    assert codehost.create_issue.call_args.kwargs["marker"] == "mnemo:action:a1"
    assert repo.materialize_action.call_args.kwargs["artifact_ref"] == "https://github.com/o/r/issues/9"


def test_approve_quarantine_materializes_debt_ticket():
    repo = MagicMock()
    repo.get_action.return_value = {
        "id": "a2", "org_id": "o", "kind": "quarantine", "status": "proposed",
        "payload": {"debt_ticket": {"title": "[Flaky] t", "body": "B", "labels": ["flaky"]},
                    "annotation": {"test_name": "t"}}}
    repo.approve_action.return_value = True
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "https://github.com/o/r/issues/22"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a2")
    assert out["materialized"] is True and out["artifact_ref"] == "https://github.com/o/r/issues/22"
    kw = codehost.create_issue.call_args.kwargs
    assert kw["title"] == "[Flaky] t" and kw["body"] == "B"


def test_approve_rejected_or_missing_returns_false():
    repo = MagicMock()
    repo.get_action.return_value = None
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    assert svc.approve_action(user_id="u", action_id="x") == {
        "approved": False, "materialized": False, "artifact_ref": None}
    codehost.create_issue.assert_not_called()
    repo.approve_action.assert_not_called()


def test_approve_already_materialized_is_idempotent():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "org_id": "o", "kind": "ticket",
                                    "status": "materialized",
                                    "artifact_ref": "https://github.com/o/r/issues/1", "payload": {}}
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "materialized": True,
                   "artifact_ref": "https://github.com/o/r/issues/1"}
    codehost.create_issue.assert_not_called()
    repo.approve_action.assert_not_called()


def test_approve_retries_materialize_when_already_approved():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "org_id": "o", "kind": "ticket", "status": "approved",
                                    "artifact_ref": None,
                                    "payload": {"title": "T", "body": "B", "labels": []}}
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "https://github.com/o/r/issues/7"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out["materialized"] is True and out["artifact_ref"] == "https://github.com/o/r/issues/7"
    repo.approve_action.assert_not_called()         # ya estaba approved
    codehost.create_issue.assert_called_once()


def test_approve_self_heal_stays_approved_without_materializing():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a3", "org_id": "o", "kind": "self_heal",
                                    "status": "proposed", "payload": {"suggested_locator": "x"}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a3")
    assert out == {"approved": True, "materialized": False, "artifact_ref": None}
    codehost.create_issue.assert_not_called()
    repo.materialize_action.assert_not_called()
```

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_actions_service.py -q`
Expected: FAIL (constructor no acepta `codehost_factory`; flujo viejo).

- [ ] **Step 4: Reescribir `src/actions/service.py`**:

```python
from typing import Any, Callable, Dict, Optional

from src.actions.base import Actuator, CodeHost, NullCodeHost

_CATEGORIES = ("quarantine", "ticket", "self_heal")


class ActionService:
    """Orquesta la capa de acción. Nivel 2: nada externo sin approve. La materialización
    es por-org (codehost_factory) y reintentable (proposed→approved→materialized)."""

    def __init__(self, *, repo, actuators: Dict[str, Actuator],
                 actions_repo=None,
                 codehost_factory: Optional[Callable[[str, str], CodeHost]] = None):
        self.repo = repo                                  # lecturas de contexto (assurance)
        self.actions_repo = actions_repo or repo          # CRUD de acciones
        self.actuators = actuators
        self._codehost_factory = codehost_factory or (lambda org_id, user_id: NullCodeHost())

    def propose_actions(self, *, user_id: str, run_id: str) -> Dict[str, int]:
        verdicts = self.repo.get_run_actionable_verdicts(user_id=user_id, run_id=run_id)
        counts = {c: 0 for c in _CATEGORIES}
        counts["skipped"] = 0
        proposals = []
        org_id = None
        for v in verdicts:
            org_id = v.get("org_id") or org_id
            actuator = self.actuators.get(v["category"])
            if actuator is None:
                counts["skipped"] += 1
                continue
            proposal = actuator.propose(v, self._context_for(user_id, v))
            if proposal is None:
                counts["skipped"] += 1
                continue
            proposals.append({
                "triage_verdict_id": v["verdict_id"], "kind": proposal.kind,
                "payload": proposal.payload, "summary": proposal.summary,
            })
            counts[proposal.kind] = counts.get(proposal.kind, 0) + 1
        if proposals and org_id:
            self.actions_repo.save_actions(user_id=user_id, org_id=org_id,
                                           run_id=run_id, actions=proposals)
        return counts

    def _context_for(self, user_id: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"test_name": verdict.get("test_name")}
        category = verdict["category"]
        if category == "real" and verdict.get("defect_family_id"):
            fam = self.repo.get_family_with_failures(
                user_id=user_id, defect_id=verdict["defect_family_id"]
            )
            if fam:
                ctx["family"] = fam.get("family") or {}
                ctx["failures"] = fam.get("failures") or []
        elif category == "maintenance" and verdict.get("failure_id"):
            sh = self.repo.get_selfheal_context(user_id=user_id, failure_id=verdict["failure_id"])
            if sh:
                ctx.update(sh)
        return ctx

    def approve_action(self, *, user_id: str, action_id: str) -> Dict[str, Any]:
        action = self.actions_repo.get_action(user_id=user_id, action_id=action_id)
        if action is None or action.get("status") == "rejected":
            return {"approved": False, "materialized": False, "artifact_ref": None}
        if action.get("status") == "materialized":
            return {"approved": True, "materialized": True,
                    "artifact_ref": action.get("artifact_ref")}
        if action.get("status") == "proposed":
            if not self.actions_repo.approve_action(user_id=user_id, action_id=action_id):
                # carrera: alguien más cambió el estado; re-leer
                action = self.actions_repo.get_action(user_id=user_id, action_id=action_id)
                if action is None or action.get("status") not in ("approved", "materialized"):
                    return {"approved": False, "materialized": False, "artifact_ref": None}
                if action.get("status") == "materialized":
                    return {"approved": True, "materialized": True,
                            "artifact_ref": action.get("artifact_ref")}
        # aquí status == 'approved' (recién o de un intento previo)
        if action["kind"] == "self_heal":
            return {"approved": True, "materialized": False, "artifact_ref": None}  # PR = F3c-2
        codehost = self._codehost_factory(action["org_id"], user_id)
        ref = self._materialize(action, codehost)
        self.actions_repo.materialize_action(user_id=user_id, action_id=action_id, artifact_ref=ref)
        return {"approved": True, "materialized": True, "artifact_ref": ref}

    def _materialize(self, action: Dict[str, Any], codehost: CodeHost) -> str:
        payload = action.get("payload") or {}
        marker = f"mnemo:action:{action['id']}"
        if action["kind"] == "ticket":
            return codehost.create_issue(
                title=payload.get("title", ""), body=payload.get("body", ""),
                labels=payload.get("labels", []), marker=marker,
            )
        if action["kind"] == "quarantine":
            dt = payload.get("debt_ticket") or {}
            return codehost.create_issue(
                title=dt.get("title", ""), body=dt.get("body", ""),
                labels=dt.get("labels", []), marker=marker,
            )
        return "stub://unknown"

    def reject_action(self, *, user_id: str, action_id: str, reason: str = "") -> bool:
        return self.actions_repo.reject_action(user_id=user_id, action_id=action_id, reason=reason)
```

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_actions_service.py -q`
Expected: PASS (los tests de `propose_*` siguen verdes porque `actions_repo` cae en `repo` cuando no se pasa).

- [ ] **Step 6: Commit**

```bash
git add src/actions/base.py src/actions/service.py tests/test_actions_service.py
git commit -m "feat(actions): codehost_factory por-org + flujo approve→materialize (self_heal queda approved)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 6: Wiring en `api_v2` (factory real perezoso, approve materializa, whitelist status)

**Files:**
- Modify: `src/api_v2.py`, `src/multitenant_models.py`
- Test: `tests/test_api_v2_actions.py`

**Interfaces:**
- Consumes: `ActionRepository`, `GitHubAppAuth`, `GitHubCodeHost`/`GitHubError`/`GitHubAuthError`, `IntegrationsRepository.get_github_config`.
- Produces: `get_action_repo() -> ActionRepository`; `ActionApproveResponse{approved, materialized, artifact_ref}`; `ActionResponse.org_id`.

- [ ] **Step 1: Actualizar modelos** en `src/multitenant_models.py`:

```python
class ActionApproveResponse(BaseModel):
    approved: bool
    materialized: bool = False
    artifact_ref: Optional[str] = None
```

Y añadir `org_id` a `ActionResponse` (campo nuevo, justo bajo `run_id`):

```python
    org_id: Optional[str] = None
```

- [ ] **Step 2: Escribir/actualizar los tests de endpoint** en `tests/test_api_v2_actions.py`.

Extender `_client` para que `repo=` overridee también `get_action_repo` (el inbox vive ahora en `ActionRepository`): dentro de `_client`, donde overridea `get_assurance_repo`, dejar las dos líneas hermanas:

```python
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
        app.dependency_overrides[api_v2.get_action_repo] = lambda: repo
```

Actualizar `test_approve_and_reject` (la respuesta de approve ahora trae `materialized`):

```python
def test_approve_and_reject():
    svc = MagicMock()
    svc.approve_action.return_value = {"approved": True, "materialized": True,
                                       "artifact_ref": "https://github.com/o/r/issues/1"}
    svc.reject_action.return_value = True
    client = _client(service=svc)
    body = client.post("/v2/actions/a1/approve").json()
    assert body["approved"] is True and body["materialized"] is True
    assert client.post("/v2/actions/a1/reject", json={"reason": "dup"}).status_code == 200
    svc.approve_action.assert_called_once_with(user_id="user-1", action_id="a1")
```

Añadir:

```python
def test_approve_github_not_configured_is_400():
    svc = MagicMock()
    svc.approve_action.side_effect = ValueError("GitHub no configurado para el org")
    assert _client(service=svc).post("/v2/actions/a1/approve").status_code == 400


def test_approve_github_api_error_is_502():
    from src.ci.github_app import GitHubError
    svc = MagicMock()
    svc.approve_action.side_effect = GitHubError("boom")
    assert _client(service=svc).post("/v2/actions/a1/approve").status_code == 502


def test_approve_github_app_unconfigured_is_503():
    from src.ci.github_auth import GitHubAuthError
    svc = MagicMock()
    svc.approve_action.side_effect = GitHubAuthError("no app")
    assert _client(service=svc).post("/v2/actions/a1/approve").status_code == 503


def test_list_actions_invalid_status_is_400():
    assert _client(repo=MagicMock()).get("/v2/actions?org_id=o1&status=bogus").status_code == 400
```

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_api_v2_actions.py -q -k "approve or status"`
Expected: FAIL (approve no mapea ValueError/GitHubError/GitHubAuthError; status no se valida).

- [ ] **Step 4: Implementar el wiring** en `src/api_v2.py`.

(a) Imports nuevos (junto a los otros):

```python
from src.actions.repository import ActionRepository
from src.ci.github_app import GitHubCodeHost, GitHubError
from src.ci.github_auth import GitHubAppAuth, GitHubAuthError
```

(b) Singletons nuevos (junto a `_action_service = None`):

```python
_action_repo = None
_github_auth = None


def get_action_repo() -> ActionRepository:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _action_repo
    if _action_repo is None:
        _action_repo = ActionRepository()
    return _action_repo


def _get_github_auth() -> GitHubAppAuth:
    global _github_auth
    if _github_auth is None:
        _github_auth = GitHubAppAuth()   # lee env perezosamente
    return _github_auth


def _github_codehost_factory(org_id: str, user_id: str) -> GitHubCodeHost:
    cfg = get_integrations_repo().get_github_config(user_id=user_id, org_id=org_id)
    if not cfg.get("configured"):
        raise ValueError("GitHub no configurado para el org")
    return GitHubCodeHost(auth=_get_github_auth(),
                          installation_id=cfg["installation_id"],
                          repo_full_name=cfg["repo_full_name"])
```

(c) Reescribir `get_action_service` para inyectar `actions_repo` y el factory real:

```python
def get_action_service() -> ActionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _action_service
    if _action_service is None:
        _action_service = ActionService(
            repo=get_assurance_repo(),
            actions_repo=get_action_repo(),
            actuators={
                "flaky": QuarantineActuator(),
                "real": TicketActuator(_LazyRootCauseAnalyzer()),
                "maintenance": SelfHealActuator(explainer=_LazySelfHealExplainer()),
            },
            codehost_factory=_github_codehost_factory,
        )
    return _action_service
```

(d) Mover el inbox a `ActionRepository` + whitelist de `status`, y `approve` con el nuevo mapeo de errores. Añadir la constante cerca del router:

```python
_ACTION_STATUSES = {"proposed", "approved", "rejected", "materialized"}
```

`list_actions_v2` — `get_actions` se movió a `ActionRepository` (Task 4), así que cambia la dependencia de `get_assurance_repo` a `get_action_repo` y valida `status` (reemplazar el endpoint completo):

```python
@router.get("/actions", response_model=List[ActionResponse])
def list_actions_v2(
    org_id: str,
    status: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: ActionRepository = Depends(get_action_repo),
) -> List[ActionResponse]:
    if status is not None and status not in _ACTION_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")
    try:
        rows = repo.get_actions(user_id=user.user_id, org_id=org_id, status=status)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [ActionResponse(**r) for r in rows]
```

`approve_action_v2` (reemplazar el cuerpo):

```python
@router.post("/actions/{action_id}/approve", response_model=ActionApproveResponse)
def approve_action_v2(
    action_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> ActionApproveResponse:
    try:
        return ActionApproveResponse(
            **service.approve_action(user_id=user.user_id, action_id=action_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubAuthError as exc:
        raise HTTPException(status_code=503, detail="GitHub App no configurada") from exc
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail="GitHub API error") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
```

- [ ] **Step 5: Run, expect PASS**

Run: `python3 -m pytest tests/test_api_v2_actions.py -q`
Expected: PASS.

- [ ] **Step 6: Run de toda la suite (sin integración) — sin regresiones**

Run: `python3 -m pytest -m "not integration" -q`
Expected: PASS (todos), incluyendo los nuevos de github_auth/github_app.

- [ ] **Step 7: Commit**

```bash
git add src/api_v2.py src/multitenant_models.py tests/test_api_v2_actions.py
git commit -m "feat(api): wiring F3c (ActionRepository + factory GitHub perezoso, approve materializa, whitelist status)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Riesgo residual conocido:** la idempotencia por marcador depende del índice de búsqueda de GitHub (eventual). El control primario es el estado en BD (`approve` atómico + `materialize` solo si `approved`). Un doble-approve concurrente exacto del mismo `action_id` (raro: un humano aprueba una vez) podría, en el peor caso, crear dos Issues antes de que el índice refleje el marcador. Aceptable para el MVP; el endurecimiento (lock `SELECT FOR UPDATE` o estado `materializing`) es follow-up si se observa.
- **Fuera de alcance (recordatorio):** `self_heal → PR` real (F3c-2), check runs/gate y certificado (F4), webhook entrante de GitHub para sincronizar estado (roadmap).
- **Despliegue:** aplicar `db/migrations/011_github_integration.sql`; definir `GITHUB_APP_ID` y `GITHUB_APP_PRIVATE_KEY` en el entorno del backend; registrar la GitHub App con scopes `issues:write` (+ `pull_requests:write`/`checks:write` para fases futuras) e instalarla por org.
