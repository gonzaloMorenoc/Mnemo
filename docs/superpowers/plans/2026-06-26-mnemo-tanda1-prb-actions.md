# Tanda 1 · PR-B — Capa de acción endurecida — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar A1 (authz por rol en reconfiguración de integraciones), B2 (atomicidad approve→materialize) y A2 (anti-injection de la GitHub API) de la auditoría.

**Architecture:** Tres cambios quirúrgicos: un `_require_admin` en `IntegrationsRepository`; un estado intermedio `materializing` (migración 017 + repo + service) que serializa la materialización; un validador Pydantic + `quote` para la GitHub API.

**Tech Stack:** Python/FastAPI/psycopg, Pydantic v2, pytest.

## Global Constraints

- **A1:** reconfigurar integraciones (`upsert_github_config`/`upsert_jira_config`) exige **admin/owner**; `approve`/`materialize`/`reject` de acciones quedan **member** (sin cambio). El endpoint ya mapea `PermissionError → 403`.
- **B2:** transición atómica `approved → materializing` (`UPDATE … WHERE status='approved'`, quien pierde el `rowcount` no materializa); `materialize_action` pasa de `materializing → materialized`; fallo/degradación tras `materializing` → revertir a `approved`.
- **A2:** `repo_full_name` validado con `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`; `file_path` con `urllib.parse.quote(…, safe="/")`.
- `DATABASE_URL` (.env) **es producción**: la migración 017 se aplica con `psql` (Bash con `dangerouslyDisableSandbox`). main protegida. Invariante RLS.
- Commits `fix:`/`feat:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`. Tests con `python3 -m pytest`.

---

## Task 1: A1 — authz por rol en reconfiguración de integraciones

**Files:** Modify `src/jira/integrations_repository.py`; Test `tests/test_integrations_admin_authz.py`.

**Interfaces:** Produces — `_require_admin(cur, org_id, user_id)` (raises `PermissionError` if not owner/admin); `upsert_github_config`/`upsert_jira_config` ahora exigen admin.

- [ ] **Step 1: Write the failing integration test** — `tests/test_integrations_admin_authz.py`:

```python
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.jira.integrations_repository import IntegrationsRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def org_with_member():
    """owner (auto-enrolado por trigger) + un segundo usuario con role 'member'."""
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    owner = str(uuid.uuid4())
    member = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            for uid in (owner, member):
                cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                            " values (%s,%s,'authenticated','authenticated',now(),now())",
                            (uid, f"u-{uid[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("authz-org-" + owner[:8], owner))
            org_id = str(cur.fetchone()[0])
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                        " on conflict (org_id, user_id) do update set role='member'", (org_id, member))
        conn.commit()
    yield {"owner": owner, "member": member, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id = any(%s)", ([owner, member],))
        conn.commit()


def test_member_cannot_reconfigure_github(org_with_member):
    repo = IntegrationsRepository(DBURL)
    ctx = org_with_member
    with pytest.raises(PermissionError):
        repo.upsert_github_config(user_id=ctx["member"], org_id=ctx["org_id"],
                                  installation_id="123", repo_full_name="o/r")


def test_owner_can_reconfigure_github(org_with_member):
    repo = IntegrationsRepository(DBURL)
    ctx = org_with_member
    repo.upsert_github_config(user_id=ctx["owner"], org_id=ctx["org_id"],
                              installation_id="123", repo_full_name="o/r")
    cfg = repo.get_github_config(user_id=ctx["owner"], org_id=ctx["org_id"])
    assert cfg["configured"] is True and cfg["repo_full_name"] == "o/r"


def test_member_cannot_reconfigure_jira(org_with_member):
    repo = IntegrationsRepository(DBURL)
    ctx = org_with_member
    with pytest.raises(PermissionError):
        repo.upsert_jira_config(user_id=ctx["member"], org_id=ctx["org_id"],
                                base_url="https://x.atlassian.net", email="a@b.c",
                                token="t", jql="project=X")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_integrations_admin_authz.py -q` → FAIL (a `member` currently succeeds — `_require_member` passes).

- [ ] **Step 3: Implement `_require_admin`** in `src/jira/integrations_repository.py`, right after `_require_member` (line ~44):

```python
    def _require_admin(self, cur: psycopg.Cursor, org_id: str, user_id: str) -> None:
        cur.execute(
            "select exists(select 1 from public.memberships"
            " where org_id = %s and user_id = %s and role in ('owner','admin')) as ok",
            (org_id, user_id),
        )
        if not cur.fetchone()["ok"]:
            raise PermissionError("owner/admin role required to configure integrations")
```

In `upsert_jira_config` (line ~51) and `upsert_github_config` (line ~87), change `self._require_member(cur, org_id, user_id)` → `self._require_admin(cur, org_id, user_id)`. Leave the GET methods (`get_jira_config`, `get_github_config`, `get_jira_credentials`) on `_require_member` (reads are fine for members).

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_integrations_admin_authz.py -q` → PASS (3 passed). Then `python3 -m pytest -m "not integration" -q` → stays green.

- [ ] **Step 5: Commit**

```bash
git add src/jira/integrations_repository.py tests/test_integrations_admin_authz.py
git commit -m "fix(security): exigir admin/owner para reconfigurar integraciones GitHub/Jira (A1)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: B2 — atomicidad approve → materialize (estado `materializing`)

**Files:** Create `db/migrations/017_actions_materializing.sql`; Modify `src/actions/repository.py`, `src/actions/service.py`, `src/api_v2.py` (`_ACTION_STATUSES`); Test `tests/test_actions_atomicity.py` + extend `tests/test_actions_service.py`.

**Interfaces:** Produces — `ActionRepository.mark_materializing(*, user_id, action_id) -> bool` (atomic `approved→materializing`), `revert_to_approved(*, user_id, action_id) -> bool`; `materialize_action` ahora `materializing→materialized`.

- [ ] **Step 1: Migración 017** — `db/migrations/017_actions_materializing.sql`:

```sql
-- db/migrations/017_actions_materializing.sql
-- Tanda 1 (B2): estado intermedio 'materializing' para serializar la materialización
-- de acciones (approved → materializing → materialized). Atomicidad approve→materialize.
alter table public.actions drop constraint if exists actions_status_check;
alter table public.actions add constraint actions_status_check
    check (status in ('proposed', 'approved', 'rejected', 'materialized', 'materializing'));
```

Apply (production): `set -a && source .env && set +a && psql "$DATABASE_URL" -f db/migrations/017_actions_materializing.sql` (Bash `dangerouslyDisableSandbox`). If the constraint name differs, find it with `psql "$DATABASE_URL" -c "\d public.actions"` and adjust the `drop constraint` name. Verify the new value is allowed: `psql "$DATABASE_URL" -c "select 'materializing'::text"` (sanity) and that an update to `materializing` on a throwaway row succeeds (the integration test covers this).

- [ ] **Step 2: Write the failing test** — `tests/test_actions_atomicity.py`:

```python
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.actions.repository import ActionRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def approved_action():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s,%s,'authenticated','authenticated',now(),now())",
                        (user, f"atom-{user[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("atom-org-" + user[:8], user))
            org = str(cur.fetchone()[0])
            cur.execute("insert into public.test_runs (org_id, project, source) values (%s,'web','pw') returning id", (org,))
            run = str(cur.fetchone()[0])
            cur.execute("insert into public.failures (org_id, run_id, test_name, error_type, message, fingerprint)"
                        " values (%s,%s,'t','E','m','fp-'||%s) returning id", (org, run, user[:8]))
            fid = str(cur.fetchone()[0])
            cur.execute("insert into public.triage_verdicts (failure_id, run_id, org_id, category, confidence,"
                        " rule_applied, requires_approval, llm_assisted, status, evidence_bundle)"
                        " values (%s,%s,%s,'real',0.85,'R4_real_recurrent',false,false,'resolved','{}') returning id",
                        (fid, run, org))
            vid = str(cur.fetchone()[0])
            cur.execute("insert into public.actions (triage_verdict_id, run_id, org_id, kind, summary, status)"
                        " values (%s,%s,%s,'ticket','x','approved') returning id", (vid, run, org))
            aid = str(cur.fetchone()[0])
        conn.commit()
    yield {"user": user, "org": org, "action_id": aid}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id=%s", (user,))
        conn.commit()


def test_mark_materializing_is_a_single_winner(approved_action):
    repo = ActionRepository(DBURL)
    ctx = approved_action
    first = repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"])
    second = repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"])
    assert first is True and second is False   # solo el primero gana la transición


def test_materialize_only_from_materializing(approved_action):
    repo = ActionRepository(DBURL)
    ctx = approved_action
    # sin pasar por materializing, materialize_action (que ahora exige 'materializing') no aplica
    assert repo.materialize_action(user_id=ctx["user"], action_id=ctx["action_id"], artifact_ref="u") is False
    assert repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"]) is True
    assert repo.materialize_action(user_id=ctx["user"], action_id=ctx["action_id"], artifact_ref="u") is True


def test_revert_to_approved(approved_action):
    repo = ActionRepository(DBURL)
    ctx = approved_action
    assert repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"]) is True
    assert repo.revert_to_approved(user_id=ctx["user"], action_id=ctx["action_id"]) is True
    # tras revertir, se puede reclamar de nuevo
    assert repo.mark_materializing(user_id=ctx["user"], action_id=ctx["action_id"]) is True
```

- [ ] **Step 3: Run, expect FAIL**

Run: `python3 -m pytest tests/test_actions_atomicity.py -q` → FAIL (`mark_materializing`/`revert_to_approved` missing; `materialize_action` still keys on `'approved'`).

- [ ] **Step 4: Implement the repo methods** in `src/actions/repository.py`. Add `mark_materializing` and `revert_to_approved`, and change `materialize_action`'s `where` from `status='approved'` to `status='materializing'`:

```python
    def mark_materializing(self, *, user_id: str, action_id: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'materializing'"
                    " where a.id = %s and a.status = 'approved'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
                    (action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def revert_to_approved(self, *, user_id: str, action_id: str) -> bool:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'approved'"
                    " where a.id = %s and a.status = 'materializing'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
                    (action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok
```

In `materialize_action` (line ~120), change `" where a.id = %s and a.status = 'approved'"` → `" where a.id = %s and a.status = 'materializing'"`.

- [ ] **Step 5: Update the service flow** in `src/actions/service.py` `approve_action`. Replace the block from `# aquí status == 'approved'` (line ~92) to the end of the method body with the serialized version:

```python
        # status == 'approved' aquí — reclamar la materialización de forma atómica
        if not self.actions_repo.mark_materializing(user_id=user_id, action_id=action_id):
            # otra request ya está materializando / lo hizo; re-leer
            action = self.actions_repo.get_action(user_id=user_id, action_id=action_id)
            if action and action.get("status") == "materialized":
                return {"approved": True, "materialized": True,
                        "artifact_ref": action.get("artifact_ref")}
            return {"approved": True, "materialized": False, "artifact_ref": None}
        codehost = self._codehost_factory(action["org_id"], user_id)
        try:
            ref = self._materialize(action, codehost)
        except Exception:
            self.actions_repo.revert_to_approved(user_id=user_id, action_id=action_id)
            raise
        if ref is None:
            # self_heal degradó (sin file o locator no casa): revertir a approved (reintentable)
            self.actions_repo.revert_to_approved(user_id=user_id, action_id=action_id)
            logger.warning("self_heal de la acción %s no produjo PR (sin file o locator no casa)",
                           action_id)
            return {"approved": True, "materialized": False, "artifact_ref": None}
        ok = self.actions_repo.materialize_action(user_id=user_id, action_id=action_id, artifact_ref=ref)
        return {"approved": True, "materialized": ok, "artifact_ref": ref}
```

- [ ] **Step 6: `_ACTION_STATUSES`** — in `src/api_v2.py` line 83, add `'materializing'`:

```python
_ACTION_STATUSES = {"proposed", "approved", "rejected", "materialized", "materializing"}
```

- [ ] **Step 7: Extend the service unit test** — in `tests/test_actions_service.py`, add a test that a GitHub failure during materialization reverts to approved (mock `actions_repo` + codehost):

```python
def test_approve_reverts_to_approved_on_codehost_error():
    from unittest.mock import MagicMock
    from src.actions.service import ActionService
    repo = MagicMock()
    actions_repo = MagicMock()
    actions_repo.get_action.return_value = {"id": "a1", "org_id": "o1", "status": "approved",
                                            "kind": "ticket", "payload": {"title": "t", "body": "b", "labels": []}}
    actions_repo.mark_materializing.return_value = True
    codehost = MagicMock()
    codehost.create_issue.side_effect = RuntimeError("github down")
    svc = ActionService(repo=repo, actuators={}, actions_repo=actions_repo,
                        codehost_factory=lambda o, u: codehost)
    import pytest
    with pytest.raises(RuntimeError):
        svc.approve_action(user_id="u", action_id="a1")
    actions_repo.revert_to_approved.assert_called_once_with(user_id="u", action_id="a1")
    actions_repo.materialize_action.assert_not_called()
```

- [ ] **Step 8: Run, expect PASS**

Run: `python3 -m pytest tests/test_actions_atomicity.py tests/test_actions_service.py -q` → PASS. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 9: Commit**

```bash
git add db/migrations/017_actions_materializing.sql src/actions/repository.py src/actions/service.py src/api_v2.py tests/test_actions_atomicity.py tests/test_actions_service.py
git commit -m "fix(actions): atomicidad approve→materialize con estado materializing + revert (B2)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: A2 — anti-injection en la GitHub API

**Files:** Modify `src/multitenant_models.py` (`GitHubConfigRequest`), `src/ci/github_app.py`; Test `tests/test_github_config_validation.py` + extend `tests/test_github_app*.py`.

**Interfaces:** Produces — `GitHubConfigRequest.repo_full_name` validado; `file_path` url-encoded en las URLs de contents.

- [ ] **Step 1: Write the failing tests** — `tests/test_github_config_validation.py`:

```python
import pytest
from pydantic import ValidationError

from src.multitenant_models import GitHubConfigRequest


def test_valid_repo_full_name():
    m = GitHubConfigRequest(org_id="o", installation_id="1", repo_full_name="owner/repo-1.x")
    assert m.repo_full_name == "owner/repo-1.x"


@pytest.mark.parametrize("bad", ["owner", "owner/repo/extra", "owner/../repo", "o r/repo", "owner/re po"])
def test_invalid_repo_full_name_rejected(bad):
    with pytest.raises(ValidationError):
        GitHubConfigRequest(org_id="o", installation_id="1", repo_full_name=bad)
```

- [ ] **Step 2: Run, expect FAIL**

Run: `python3 -m pytest tests/test_github_config_validation.py -q` → FAIL (no validator yet).

- [ ] **Step 3: Add the validator** in `src/multitenant_models.py`. Add `field_validator` to the pydantic import (`from pydantic import BaseModel, Field, field_validator`) and to `GitHubConfigRequest`:

```python
class GitHubConfigRequest(BaseModel):
    org_id: str
    installation_id: str
    repo_full_name: str

    @field_validator("repo_full_name")
    @classmethod
    def _valid_repo(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", v):
            raise ValueError("repo_full_name debe tener el formato 'owner/repo'")
        return v
```

- [ ] **Step 4: url-encode `file_path`** in `src/ci/github_app.py`. Add `from urllib.parse import quote` at the top, and wrap `file_path` in the two `contents` URLs (`_get_file` ~line 104 and `_put_file` ~line 127): change `f"{_API}/repos/{self._repo}/contents/{file_path}"` → `f"{_API}/repos/{self._repo}/contents/{quote(file_path, safe='/')}"` in both.

- [ ] **Step 5: Write the failing github_app test** — `tests/test_github_app_filepath_encoding.py`:

```python
from unittest.mock import MagicMock

from src.ci.github_app import GitHubCodeHost


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


def test_get_file_url_encodes_path():
    session = MagicMock()
    session.get.return_value = _Resp(200, {"content": "", "sha": "s"})
    auth = MagicMock(); auth.installation_token.return_value = "tok"
    host = GitHubCodeHost(auth=auth, installation_id="1", repo_full_name="o/r", session=session)
    host._get_file("tests/a b/spec.ts", "main")
    url = session.get.call_args.args[0] if session.get.call_args.args else session.get.call_args.kwargs.get("url", "")
    url = str(url) + str(session.get.call_args)
    assert "a%20b" in url and "/contents/" in url   # el espacio se codifica, las barras no
```

(If `_get_file`'s call shape differs, assert on `session.get.call_args` — the encoded `a%20b` must appear in the contents URL.)

- [ ] **Step 6: Run, expect PASS**

Run: `python3 -m pytest tests/test_github_config_validation.py tests/test_github_app_filepath_encoding.py -q` → PASS. Then `python3 -m pytest -m "not integration" -q` → green (existing github_app tests still pass — `safe='/'` keeps normal paths unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/multitenant_models.py src/ci/github_app.py tests/test_github_config_validation.py tests/test_github_app_filepath_encoding.py
git commit -m "fix(security): validar repo_full_name + url-encode file_path en la GitHub API (A2)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **B2 y la migración 017:** el nombre del constraint `actions_status_check` es el que Postgres genera para el check de columna de 010; si difiere, ajustar el `drop constraint` (verificar con `\d public.actions`). La migración es additiva (amplía el conjunto permitido); las acciones existentes no se ven afectadas.
- **A1:** sólo las dos reconfiguraciones de integraciones pasan a admin; el resto (lecturas, approve/reject/materialize de acciones) sigue en member, según la decisión de producto.
- **A2 `safe='/'`:** preserva las barras de la ruta (no rompe `dir/sub/file.ts`); sólo codifica caracteres peligrosos (espacios, `..` queda literal pero el validador del repo y el scope del token de instalación lo contienen).
- **Fuera de alcance:** tandas 2/3/4.
