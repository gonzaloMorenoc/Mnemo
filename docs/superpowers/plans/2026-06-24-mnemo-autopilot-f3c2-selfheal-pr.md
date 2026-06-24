# F3c-2 — self_heal → PR borrador real — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Al aprobar una acción `self_heal`, abrir un PR borrador real en GitHub que cura el locator (reemplaza `broken_locator` por `suggested_locator` en el archivo del test), de forma determinista, idempotente y aislada por org.

**Architecture:** Persistir el `file` del test (que el reporter ya emite) por la cadena de ingesta hasta el payload de self_heal. Implementar `GitHubCodeHost.open_draft_pr` (refs/contents/pulls + string-replace determinista). Cablear `ActionService.approve_action` para que `self_heal` materialice el PR; degrada (queda `approved`, sin PR) si falta `file` o el locator no casa.

**Tech Stack:** Python 3.13, FastAPI, psycopg, `requests` (cliente HTTP del repo), `base64` (stdlib), pytest (+ `@pytest.mark.integration` para Postgres).

## Global Constraints

- **Determinista y auditable:** el diff es un `str.replace(broken, suggested, 1)` exacto; sin LLM en el camino del cambio.
- **Idempotencia:** branch determinista `mnemo/self-heal/{action_id}` (derivado del `marker`); si el PR para ese `head` ya existe → reusar, no duplicar.
- **Degradación elegante:** `file` ausente o locator no presente en el archivo → `open_draft_pr` devuelve `None` → la acción queda `approved` (materialized:False) + `logger.warning`; reintentable. NO se abre PR vacío ni Issue de fallback (YAGNI). `GitHubError` (API real) → 502.
- **Nivel 2:** solo PR `draft=true` tras un `approve` válido; nunca auto-merge.
- **Aislamiento por-org:** el repo destino es el del org (config de F3c); membership ya validado en `get_action`.
- **Cliente HTTP = `requests`** con `timeout=15` en cada llamada; errores de API → `GitHubError`.
- **Migración idempotente** (`add column if not exists`). SQL parametrizado.
- **Commits** terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`. Ejecutar tests con `python3 -m pytest`.

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `db/migrations/012_failure_location.sql` | crear | `failures.file` + `failures.line` |
| `src/ingest/models.py` | modificar | `FailureRecord` gana `file`/`line` |
| `src/ci/mapping.py` | modificar | `to_failure_records` pasa `file`/`line` |
| `src/defects/repository.py` | modificar | INSERT `failures` con `file`/`line`; `get_selfheal_context` devuelve `file` |
| `src/actions/selfheal/selfheal.py` | modificar | payload de self_heal incluye `file` |
| `src/actions/base.py` | modificar | firma `open_draft_pr` → `Optional[str]` |
| `src/ci/github_app.py` | modificar | `GitHubCodeHost.open_draft_pr` (refs/contents/pulls) |
| `src/actions/service.py` | modificar | `_materialize` maneja `self_heal`; `approve_action` cablea |
| `tests/test_ci_mapping.py` | modificar | file/line en records |
| `tests/test_selfheal_actuator.py` | modificar | payload con file |
| `tests/test_actions_repository.py` | modificar | `get_selfheal_context` devuelve file (integración) |
| `tests/test_github_app.py` | modificar | `open_draft_pr` (flujo + idempotencia + degrada) |
| `tests/test_actions_service.py` | modificar | approve self_heal → PR / degrada |

---

## Task 1: Persistir `file`/`line` en la ingesta

**Files:**
- Create: `db/migrations/012_failure_location.sql`
- Modify: `src/ingest/models.py`, `src/ci/mapping.py`, `src/defects/repository.py`, `src/actions/selfheal/selfheal.py`
- Test: `tests/test_ci_mapping.py`, `tests/test_selfheal_actuator.py`, `tests/test_actions_repository.py`

**Interfaces:**
- Produces: `FailureRecord` con `file: Optional[str] = None`, `line: Optional[int] = None`. `get_selfheal_context(...)` añade `"file"` a su dict de retorno. El payload de `self_heal` gana `"file"`.

- [ ] **Step 1: Migración**

Create `db/migrations/012_failure_location.sql`:

```sql
-- db/migrations/012_failure_location.sql
-- F3c-2: ubicación del test (file:line) para el self-heal → PR. El reporter ya
-- emite file/line (CiTestResult); aquí se persisten para localizar el archivo a editar.

alter table public.failures add column if not exists file text;
alter table public.failures add column if not exists line int;
```

Aplicar a la BD de tests (DATABASE_URL en `.env`):
`set -a && source .env && set +a && psql "$DATABASE_URL" -f db/migrations/012_failure_location.sql`

- [ ] **Step 2: `FailureRecord` gana file/line**

In `src/ingest/models.py`, replace the dataclass:

```python
@dataclass
class FailureRecord:
    test_name: str
    error_type: Optional[str]
    message: str
    trace: Optional[str]
    project: str
    source: str  # allure | junit | testng | cucumber | playwright | cypress | robot
    file: Optional[str] = None
    line: Optional[int] = None
```

- [ ] **Step 3: Test RED — `to_failure_records` lleva file/line**

In `tests/test_ci_mapping.py`, add:

```python
def test_carries_file_and_line():
    art = _art([{"test_name": "c", "status": "fail", "message": "boom",
                 "file": "tests/checkout.spec.ts", "line": 42}])
    rec = to_failure_records(art)[0]
    assert rec.file == "tests/checkout.spec.ts" and rec.line == 42


def test_file_line_default_none_when_absent():
    art = _art([{"test_name": "c", "status": "fail", "message": "boom"}])
    rec = to_failure_records(art)[0]
    assert rec.file is None and rec.line is None
```

Run: `python3 -m pytest tests/test_ci_mapping.py::test_carries_file_and_line -q` → FAIL (file is None).

- [ ] **Step 4: Implement — `to_failure_records` pasa file/line**

In `src/ci/mapping.py`, in the `FailureRecord(...)` construction, add the two fields:

```python
        records.append(
            FailureRecord(
                test_name=t.test_name,
                error_type=t.error_type or parse_error_type(t.message),
                message=t.message,
                trace=t.trace,
                project=artifact.project,
                source=artifact.source,
                file=t.file,
                line=t.line,
            )
        )
```

Run: `python3 -m pytest tests/test_ci_mapping.py -q` → PASS.

- [ ] **Step 5: INSERT de `failures` con file/line**

In `src/defects/repository.py`, in `_match_and_insert_failure`, update the failures INSERT (the columns list and the values tuple):

```python
        cur.execute(
            """
            insert into public.failures
                (run_id, org_id, test_name, error_type, message, trace,
                 fingerprint, embedding, sanitized, defect_family_id,
                 external_ref, external_url, file, line)
            values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s, %s)
            """,
            (run_id, org_id, item.rec.test_name, item.rec.error_type, item.rec.message,
             item.rec.trace, item.fingerprint, Vector(list(item.embedding)), family_id,
             item.external_ref, item.external_url, item.rec.file, item.rec.line),
        )
```

- [ ] **Step 6: `get_selfheal_context` devuelve `file`**

In `src/defects/repository.py`, in `get_selfheal_context`, add `f.file` to the first SELECT and `file` to the returned dict:

```python
            cur.execute(
                "select f.message, f.trace, f.test_name, f.file, r.org_id, r.project, r.commit_sha"
                " from public.failures f join public.test_runs r on r.id = f.run_id"
                " where f.id = %s and exists (select 1 from public.memberships m"
                "   where m.org_id = r.org_id and m.user_id = %s)",
                (failure_id, user_id),
            )
```
and the return dict:
```python
    return {
        "error_message": row["message"], "trace": row["trace"],
        "green_dom": green["content"] if green else None,
        "failure_dom": fail["content"] if fail else None,
        "file": row["file"],
    }
```

- [ ] **Step 7: Test RED → GREEN — integración `get_selfheal_context` devuelve file**

In `tests/test_actions_repository.py`, in `test_get_selfheal_context_returns_error_and_doms`, set `file` on the ingested record and assert it round-trips. Change the `FailureRecord(...)` in that test to include `file="tests/co.spec.ts"` and add at the end:

```python
    assert ctx["file"] == "tests/co.spec.ts"
```

Run: `python3 -m pytest tests/test_actions_repository.py -q` → PASS (needs DB + migration 012 applied).

- [ ] **Step 8: Payload de self_heal incluye `file`**

In `src/actions/selfheal/selfheal.py`, in `SelfHealActuator.propose`, add `file` to the payload dict:

```python
            return ActionProposal(
                kind="self_heal",
                payload={"broken_locator": broken_str, "suggested_locator": top.locator,
                         "candidates": cands, "reasoning": reasoning,
                         "file": context.get("file")},
                summary=f"Self-heal: {broken_str} → {top.locator}",
            )
```

- [ ] **Step 9: Test — payload incluye file**

In `tests/test_selfheal_actuator.py`, add:

```python
def test_payload_includes_file_from_context():
    p = SelfHealActuator().propose({}, _ctx(file="tests/checkout.spec.ts"))
    assert p is not None and p.payload["file"] == "tests/checkout.spec.ts"
```

Run: `python3 -m pytest tests/test_selfheal_actuator.py -q` → PASS.

- [ ] **Step 10: Full suite + commit**

Run: `python3 -m pytest -m "not integration" -q` → green. Then:

```bash
git add db/migrations/012_failure_location.sql src/ingest/models.py src/ci/mapping.py \
        src/defects/repository.py src/actions/selfheal/selfheal.py \
        tests/test_ci_mapping.py tests/test_selfheal_actuator.py tests/test_actions_repository.py
git commit -m "feat(selfheal): persistir file del test en la ingesta (migración 012 + cadena hasta el payload)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `GitHubCodeHost.open_draft_pr`

**Files:**
- Modify: `src/actions/base.py`, `src/ci/github_app.py`
- Test: `tests/test_github_app.py`

**Interfaces:**
- Consumes: `GitHubAppAuth` (vía `self._headers()`), `GitHubError`.
- Produces: `open_draft_pr(*, title, body, file_path, old_str, new_str, marker="") -> Optional[str]` — URL del PR, o `None` si `old_str` no está en el archivo (degrada). `GitHubError` en fallo de API.

- [ ] **Step 1: Firma nueva en `base.py`**

In `src/actions/base.py`, update the `CodeHost` Protocol and `NullCodeHost`:

```python
class CodeHost(Protocol):
    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str: ...
    def open_draft_pr(self, *, title: str, body: str, file_path: str,
                      old_str: str, new_str: str, marker: str = "") -> Optional[str]: ...


class NullCodeHost:
    """Stub: NO escribe en ningún sitio externo (default de tests / sin GitHub)."""

    def create_issue(self, *, title: str, body: str, labels: List[str], marker: str = "") -> str:
        return "stub://issue/pending"

    def open_draft_pr(self, *, title: str, body: str, file_path: str,
                      old_str: str, new_str: str, marker: str = "") -> Optional[str]:
        return "stub://pr/pending"
```

(`Optional` is already imported in base.py.)

- [ ] **Step 2: Test RED — `open_draft_pr` flujo feliz**

In `tests/test_github_app.py`, add (reusing the existing `_auth()` helper):

```python
import base64

REPO = "o/r"


class _PrResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _PrSess:
    """Enruta las llamadas de open_draft_pr; registra para aserciones."""

    def __init__(self, *, content="page.locator('#old')", existing_pr=None):
        self.content = content
        self.existing_pr = existing_pr
        self.put_body = None
        self.pr_body = None

    def get(self, url, params=None, headers=None, timeout=None):
        if url.endswith("/pulls"):
            return _PrResp(200, [{"html_url": self.existing_pr}] if self.existing_pr else [])
        if url.endswith(f"/repos/{REPO}"):
            return _PrResp(200, {"default_branch": "main"})
        if "/git/ref/heads/" in url:
            return _PrResp(200, {"object": {"sha": "base123"}})
        if "/contents/" in url:
            enc = base64.b64encode(self.content.encode("utf-8")).decode("utf-8")
            return _PrResp(200, {"content": enc, "sha": "filesha"})
        return _PrResp(404, {})

    def post(self, url, json=None, headers=None, timeout=None):
        if url.endswith("/git/refs"):
            return _PrResp(201, {})
        if url.endswith("/pulls"):
            self.pr_body = json
            return _PrResp(201, {"html_url": "https://github.com/o/r/pull/7"})
        return _PrResp(404, {})

    def put(self, url, json=None, headers=None, timeout=None):
        self.put_body = json
        return _PrResp(200, {"commit": {"sha": "c1"}})


def test_open_draft_pr_creates_pr_and_returns_url():
    sess = _PrSess(content="await page.locator('#old').click()")
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    url = ch.open_draft_pr(title="Self-heal", body="B", file_path="t.spec.ts",
                           old_str="locator('#old')", new_str="getByTestId('save')",
                           marker="mnemo:action:a1")
    assert url == "https://github.com/o/r/pull/7"
    # el commit lleva el contenido con el locator reemplazado
    new_content = base64.b64decode(sess.put_body["content"]).decode("utf-8")
    assert "getByTestId('save')" in new_content and "locator('#old')" not in new_content
    # PR draft, head = branch determinista, marcador en el body
    assert sess.pr_body["draft"] is True
    assert sess.pr_body["head"] == "mnemo/self-heal/a1"
    assert "<!-- mnemo:action:a1 -->" in sess.pr_body["body"]


def test_open_draft_pr_reuses_existing_pr():
    sess = _PrSess(existing_pr="https://github.com/o/r/pull/3")
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    url = ch.open_draft_pr(title="T", body="B", file_path="t.spec.ts",
                           old_str="x", new_str="y", marker="mnemo:action:a1")
    assert url == "https://github.com/o/r/pull/3"
    assert sess.put_body is None  # no commit: reusó el PR


def test_open_draft_pr_returns_none_when_locator_absent():
    sess = _PrSess(content="no hay locator aquí")
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    out = ch.open_draft_pr(title="T", body="B", file_path="t.spec.ts",
                           old_str="locator('#missing')", new_str="y", marker="mnemo:action:a1")
    assert out is None
    assert sess.pr_body is None  # no abrió PR


def test_open_draft_pr_raises_on_api_error():
    class _Boom(_PrSess):
        def get(self, url, params=None, headers=None, timeout=None):
            if url.endswith(f"/repos/{REPO}"):
                return _PrResp(500, {})
            return super().get(url, params=params, headers=headers, timeout=timeout)
    sess = _Boom()
    ch = GitHubCodeHost(auth=_auth(), installation_id="9", repo_full_name=REPO, session=sess)
    with pytest.raises(GitHubError):
        ch.open_draft_pr(title="T", body="B", file_path="t.spec.ts",
                         old_str="locator('#old')", new_str="y", marker="mnemo:action:a1")
```

Run: `python3 -m pytest tests/test_github_app.py -q -k open_draft_pr` → FAIL (`NotImplementedError`).

- [ ] **Step 3: Implement `open_draft_pr`**

In `src/ci/github_app.py`, add `import base64` at the top and replace the `open_draft_pr` stub with the implementation + private helpers:

```python
    def open_draft_pr(self, *, title: str, body: str, file_path: str,
                      old_str: str, new_str: str, marker: str = "") -> Optional[str]:
        owner = self._repo.split("/")[0]
        action_id = marker.rsplit(":", 1)[-1] if marker else "fix"
        branch = f"mnemo/self-heal/{action_id}"
        existing = self._find_pr_by_head(owner, branch)
        if existing:
            return existing
        default_branch = self._default_branch()
        base_sha = self._ref_sha(default_branch)
        content, file_sha = self._get_file(file_path, default_branch)
        new_content = content.replace(old_str, new_str, 1)
        if new_content == content:
            return None  # locator no encontrado en el archivo → degrada
        self._create_ref(branch, base_sha)
        self._put_file(file_path, new_content, file_sha, branch,
                       message=f"fix(self-heal): {old_str} -> {new_str}")
        pr_body = f"{body}\n\n<!-- {marker} -->" if marker else body
        return self._create_pr(title, pr_body, branch, default_branch)

    def _find_pr_by_head(self, owner: str, branch: str) -> Optional[str]:
        resp = self._session.get(
            f"{_API}/repos/{self._repo}/pulls",
            params={"head": f"{owner}:{branch}", "state": "all"},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            return None
        prs = resp.json()
        return prs[0]["html_url"] if prs else None

    def _default_branch(self) -> str:
        resp = self._session.get(f"{_API}/repos/{self._repo}", headers=self._headers(), timeout=15)
        if resp.status_code >= 300:
            raise GitHubError(f"get repo falló: HTTP {resp.status_code}")
        return resp.json()["default_branch"]

    def _ref_sha(self, branch: str) -> str:
        resp = self._session.get(
            f"{_API}/repos/{self._repo}/git/ref/heads/{branch}",
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"get ref falló: HTTP {resp.status_code}")
        return resp.json()["object"]["sha"]

    def _get_file(self, file_path: str, ref: str):
        resp = self._session.get(
            f"{_API}/repos/{self._repo}/contents/{file_path}",
            params={"ref": ref}, headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"get contents falló: HTTP {resp.status_code}")
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content, data["sha"]

    def _create_ref(self, branch: str, sha: str) -> None:
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code == 422:
            return  # el branch ya existe → reusa
        if resp.status_code >= 300:
            raise GitHubError(f"create ref falló: HTTP {resp.status_code}")

    def _put_file(self, file_path: str, new_content: str, file_sha: str,
                  branch: str, *, message: str) -> None:
        resp = self._session.put(
            f"{_API}/repos/{self._repo}/contents/{file_path}",
            json={"message": message,
                  "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
                  "sha": file_sha, "branch": branch},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"put contents falló: HTTP {resp.status_code}")

    def _create_pr(self, title: str, body: str, head: str, base: str) -> str:
        resp = self._session.post(
            f"{_API}/repos/{self._repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base, "draft": True},
            headers=self._headers(), timeout=15,
        )
        if resp.status_code >= 300:
            raise GitHubError(f"create PR falló: HTTP {resp.status_code}")
        return resp.json()["html_url"]
```

- [ ] **Step 4: Run → PASS + commit**

Run: `python3 -m pytest tests/test_github_app.py -q` → PASS (4 previos + 4 nuevos). Then:

```bash
git add src/actions/base.py src/ci/github_app.py tests/test_github_app.py
git commit -m "feat(github): GitHubCodeHost.open_draft_pr (refs/contents/pulls + string-replace determinista, idempotente)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Cablear `self_heal` → PR en `ActionService`

**Files:**
- Modify: `src/actions/service.py`
- Test: `tests/test_actions_service.py`

**Interfaces:**
- Consumes: `CodeHost.open_draft_pr(...) -> Optional[str]` (Task 2); el payload de `self_heal` con `file` (Task 1).

- [ ] **Step 1: Test RED — approve self_heal abre PR / degrada**

In `tests/test_actions_service.py`, replace `test_approve_self_heal_stays_approved_without_materializing` with:

```python
def test_approve_self_heal_opens_draft_pr():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a3", "org_id": "o", "kind": "self_heal", "status": "proposed",
                                    "payload": {"file": "t.spec.ts", "broken_locator": "locator('#x')",
                                                "suggested_locator": "getByTestId('x')",
                                                "reasoning": "r", "candidates": []}}
    repo.approve_action.return_value = True
    repo.materialize_action.return_value = True
    codehost = MagicMock()
    codehost.open_draft_pr.return_value = "https://github.com/o/r/pull/7"
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a3")
    assert out == {"approved": True, "materialized": True,
                   "artifact_ref": "https://github.com/o/r/pull/7"}
    kw = codehost.open_draft_pr.call_args.kwargs
    assert kw["file_path"] == "t.spec.ts" and kw["old_str"] == "locator('#x')"
    assert kw["new_str"] == "getByTestId('x')" and kw["marker"] == "mnemo:action:a3"
    codehost.create_issue.assert_not_called()


def test_approve_self_heal_no_file_degrades():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a3", "org_id": "o", "kind": "self_heal", "status": "proposed",
                                    "payload": {"suggested_locator": "x"}}  # sin file
    repo.approve_action.return_value = True
    codehost = MagicMock()
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a3")
    assert out == {"approved": True, "materialized": False, "artifact_ref": None}
    codehost.open_draft_pr.assert_not_called()
    repo.materialize_action.assert_not_called()


def test_approve_self_heal_locator_not_found_degrades():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a3", "org_id": "o", "kind": "self_heal", "status": "proposed",
                                    "payload": {"file": "t.spec.ts", "broken_locator": "locator('#x')",
                                                "suggested_locator": "y"}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    codehost.open_draft_pr.return_value = None  # locator no casa
    svc = ActionService(repo=repo, actuators={}, codehost_factory=lambda org, user: codehost)
    out = svc.approve_action(user_id="u", action_id="a3")
    assert out == {"approved": True, "materialized": False, "artifact_ref": None}
    repo.materialize_action.assert_not_called()
```

Run: `python3 -m pytest tests/test_actions_service.py -q -k self_heal` → FAIL (current short-circuit returns materialized:False without calling open_draft_pr).

- [ ] **Step 2: Implement — `_materialize` maneja self_heal; `approve_action` cablea**

In `src/actions/service.py`, add a module-level helper (after the imports / `logger`):

```python
def _self_heal_body(payload: Dict[str, Any]) -> str:
    return (
        "**Self-heal de locator** (Mnemo Autopilot, Nivel 2).\n\n"
        f"- Locator roto: `{payload.get('broken_locator', '')}`\n"
        f"- Locator sugerido: `{payload.get('suggested_locator', '')}`\n"
        f"- Archivo: `{payload.get('file', '')}`\n\n"
        f"## Razonamiento\n{payload.get('reasoning', '')}\n\n"
        "> PR borrador automático — requiere revisión humana; nunca auto-merge."
    )
```

Replace the `self_heal` short-circuit block in `approve_action` (the `if action["kind"] == "self_heal": return {...materialized: False...}` that precedes the codehost build) so the flow falls through to `_materialize`, and make `_materialize` return `Optional[str]`:

```python
        # aquí status == 'approved' (recién o de un intento previo)
        codehost = self._codehost_factory(action["org_id"], user_id)
        ref = self._materialize(action, codehost)
        if ref is None:
            # self_heal degradó (sin file o locator no casa): decisión preservada, sin PR
            logger.warning("self_heal de la acción %s no produjo PR (sin file o locator no casa)",
                           action_id)
            return {"approved": True, "materialized": False, "artifact_ref": None}
        ok = self.actions_repo.materialize_action(user_id=user_id, action_id=action_id, artifact_ref=ref)
        if not ok:
            logger.warning(
                "materialize_action no actualizó la acción %s (estado ya no 'approved'); "
                "posible doble materialización mitigada por el marcador", action_id,
            )
        return {"approved": True, "materialized": ok, "artifact_ref": ref}
```

And extend `_materialize` to handle `self_heal` and return `Optional[str]`:

```python
    def _materialize(self, action: Dict[str, Any], codehost: CodeHost) -> Optional[str]:
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
        if action["kind"] == "self_heal":
            file_path = payload.get("file")
            if not file_path:
                return None  # sin file no se puede localizar el test → degrada
            return codehost.open_draft_pr(
                title=action.get("summary") or "Self-heal de locator",
                body=_self_heal_body(payload),
                file_path=file_path,
                old_str=payload.get("broken_locator", ""),
                new_str=payload.get("suggested_locator", ""),
                marker=marker,
            )
        raise ValueError(f"_materialize: unknown action kind {action['kind']!r}")
```

(`Optional` is already imported in service.py; `_materialize` previously returned `str` and raised on unknown kind — both preserved. `ticket`/`quarantine` never return `None`, so only `self_heal` can degrade.)

- [ ] **Step 3: Run → PASS**

Run: `python3 -m pytest tests/test_actions_service.py -q` → PASS (self_heal tests + the unchanged ticket/quarantine/idempotency tests, since `ticket`/`quarantine` still return a non-None ref).

- [ ] **Step 4: Full suite + commit**

Run: `python3 -m pytest -m "not integration" -q` → green. Then:

```bash
git add src/actions/service.py tests/test_actions_service.py
git commit -m "feat(actions): approve de self_heal abre PR borrador (degrada si falta file o el locator no casa)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Despliegue:** aplicar `db/migrations/012_failure_location.sql`; la GitHub App necesita scopes `contents:write` + `pull_requests:write` (además del `issues:write` de F3c).
- **Fuera de alcance (recordatorio):** multi-archivo / Page Objects; LLM-fallback cuando el formato del locator difiere del canónico; sincronizar estado del PR vía webhook entrante; check runs/gate + certificado (F4).
- **Riesgo conocido:** el string-replace exige que el `broken_locator` canónico (comillas simples, `{ name: '...' }`) coincida con el código fuente; si difiere, degrada (no abre PR). Aceptable para el MVP (repo de demo controlado); normalización/LLM-fallback es follow-up.
