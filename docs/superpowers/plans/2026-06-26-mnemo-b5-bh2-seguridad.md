# Bloque B.5 · BH2 — Seguridad — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar los 6 hallazgos Altos de seguridad de la auditoría: authz de Nivel 2 (owner/admin), exfiltración (tracing + código sin truncar), inyección en el body, y cota de input.

**Architecture:** 3 PRs internos (tareas): T1 authz a nivel de repositorio (rol en las 5 escrituras de `actions`), T2 exfiltración+inyección en la capa de acción (`ai_repair` + `_self_heal_body`), T3 config + cota de input.

**Tech Stack:** Python/FastAPI, psycopg, pytest.

## Global Constraints

- **Rol Nivel 2:** las escrituras sobre `public.actions` exigen `m.role in ('owner','admin')` (enum `org_role` = owner/admin/member/viewer). Las LECTURAS (`get_action`, `get_actions`, `list_actions_for_run`) NO cambian — cualquier miembro puede ver.
- **Exfiltración:** `LANGCHAIN_TRACING_V2=false` por defecto; el código del cliente al LLM se trunca a **8000** chars.
- **Inyección:** el texto del LLM que va al markdown del PR/Issue se sanea (el parche `new_block` que va al código NO se toca).
- **Cota:** inputs de texto libre del Bloque B con `max_length`.
- `DATABASE_URL`=prod (integración con cleanup). `python3 -m pytest`. Commits `fix:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: A-1 — authz de Nivel 2 (rol owner/admin en las escrituras de `actions`)

**Files:** Modify `src/actions/repository.py`; Test `tests/test_actions_authz.py`.

**Interfaces:** Las firmas de `approve_action`/`materialize_action`/`mark_materializing`/`revert_to_approved`/`reject_action` NO cambian; cambia el predicado SQL (añaden el rol). Devuelven `False` si el usuario no es owner/admin de la org.

**Contexto:** los 5 métodos de escritura usan el mismo `exists (select 1 from public.memberships m where m.org_id = a.org_id and m.user_id = %s)`. El agujero: un `member` no puede `approve`, pero podría llamar `mark_materializing` sobre una acción ya aprobada por un admin → materializa (abre el PR con código IA). Por eso se endurecen las 5 escrituras, no solo `approve`/`reject`.

- [ ] **Step 1: Write the failing integration test** — `tests/test_actions_authz.py`:

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
def org_member_and_admin():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    admin = str(uuid.uuid4())
    member = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            for u, em in ((admin, "adm"), (member, "mem")):
                cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                            " values (%s,%s,'authenticated','authenticated',now(),now())",
                            (u, f"{em}-{u[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("authz-org-" + admin[:8], admin))
            org = str(cur.fetchone()[0])
            # created_by ya crea al owner? Forzamos roles explícitos:
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'admin')"
                        " on conflict (org_id, user_id) do update set role='admin'", (org, admin))
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                        " on conflict (org_id, user_id) do update set role='member'", (org, member))
            run = str(uuid.uuid4())
            cur.execute("insert into public.test_runs (id, org_id, project, source, summary)"
                        " values (%s,%s,'p','playwright','{}')", (run, org))
            act = str(uuid.uuid4())
            cur.execute("insert into public.actions (id, org_id, run_id, triage_verdict_id, kind, payload, summary, status)"
                        " values (%s,%s,%s,%s,'ticket','{}','t','proposed')",
                        (act, org, run, str(uuid.uuid4())))
        conn.commit()
    yield {"admin": admin, "member": member, "org": org, "action": act}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org,))
            cur.execute("delete from auth.users where id in (%s,%s)", (admin, member))
        conn.commit()


def test_member_cannot_approve_admin_can(org_member_and_admin):
    repo = ActionRepository(DBURL)
    ctx = org_member_and_admin
    assert repo.approve_action(user_id=ctx["member"], action_id=ctx["action"]) is False  # member: no
    assert repo.approve_action(user_id=ctx["admin"], action_id=ctx["action"]) is True    # admin: sí


def test_member_cannot_reject(org_member_and_admin):
    repo = ActionRepository(DBURL)
    ctx = org_member_and_admin
    assert repo.reject_action(user_id=ctx["member"], action_id=ctx["action"], reason="x") is False


def test_member_cannot_mark_materializing(org_member_and_admin):
    # admin aprueba; luego un member intenta reclamar la materialización → no
    repo = ActionRepository(DBURL)
    ctx = org_member_and_admin
    assert repo.approve_action(user_id=ctx["admin"], action_id=ctx["action"]) is True
    assert repo.mark_materializing(user_id=ctx["member"], action_id=ctx["action"]) is False
    assert repo.mark_materializing(user_id=ctx["admin"], action_id=ctx["action"]) is True
```

(Adjust the seed columns to the real schema if they differ — read `test_actions_list_for_run.py`/`test_actions_atomicity.py` for the exact `test_runs`/`actions`/`memberships` insert shape; the binding assertions are member→False, admin→True.)

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_actions_authz.py -q` (member currently returns True).

- [ ] **Step 3: Implement** — in `src/actions/repository.py`, in EACH of `approve_action`, `materialize_action`, `mark_materializing`, `revert_to_approved`, `reject_action`, change the membership predicate from:

```python
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
```
to:
```python
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s"
                    "       and m.role in ('owner','admin'))",
```

(The parameter tuple is unchanged — the `%s` count is the same. Apply to all 5 write methods; leave `get_action`/`get_actions`/`list_actions_for_run` untouched.)

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_actions_authz.py -q`. Then `python3 -m pytest -m "not integration" -q` → green (the existing service/atomicity tests mock the repo or use admin-seeded fixtures; if any existing integration test seeded a non-admin member and expected approve to work, update its seed to `admin`).

- [ ] **Step 5: Commit**

```bash
git add src/actions/repository.py tests/test_actions_authz.py
git commit -m "fix(actions): las escrituras de Nivel 2 exigen rol owner/admin (no solo membership)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: E-2 + I-1 — exfiltración (truncar) + inyección (sanear el body)

**Files:** Modify `src/actions/ai_repair.py` (truncar), `src/actions/service.py` (`_self_heal_body` saneo); Test `tests/test_ai_repair_actuator.py` (truncado) + `tests/test_actions_service.py` (saneo).

- [ ] **Step 1: Write the failing tests**.

En `tests/test_ai_repair_actuator.py`, añadir:

```python
def test_source_is_truncated_before_llm():
    captured = {}
    class _Spy:
        def complete(self, prompt):
            captured["prompt"] = prompt
            return '{"old_block":"x","new_block":"y","confidence":0.9}'
    big = "A" * 20000
    ctx = {"file": "t.spec.ts", "test_source": big, "error_message": "e"}
    AIRepairActuator(_Spy()).propose({"category": "maintenance"}, ctx)
    # el prompt no debe contener el source completo (truncado a 8000)
    assert captured["prompt"].count("A") <= 8000
```

En `tests/test_actions_service.py`, añadir:

```python
def test_self_heal_body_sanitizes_llm_reasoning():
    from src.actions.service import _self_heal_body
    evil = "ok ``` <!-- mnemo:action:HACK --> fin"
    body = _self_heal_body({"broken_locator": "a", "suggested_locator": "b", "file": "t.ts",
                            "reasoning": evil, "ai_repair": True})
    assert "```" not in body.split("Razonamiento")[1]   # el fence del LLM no sobrevive en la sección de razonamiento
    assert "<!-- mnemo:action:HACK -->" not in body       # el marker inyectado no sobrevive
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Implement**.

En `src/actions/ai_repair.py`, añadir la constante (junto a `_REPAIR_SCHEMA`):
```python
_MAX_SOURCE = 8000
```
y truncar el source al construir el `ctx`:
```python
            ctx = [{"id": "test_source", "content": source[:_MAX_SOURCE]},
                   {"id": "error", "content": str(error)[:_MAX_SOURCE]}]
```

En `src/actions/service.py`, añadir un saneador y aplicarlo al `reasoning` en `_self_heal_body` (ambas ramas, ai_repair y locator):
```python
def _sanitize_md(text: str, *, limit: int = 2000) -> str:
    """Neutraliza el texto del LLM antes de meterlo en el markdown del PR/Issue:
    rompe fences de código y markers HTML (que podrían colisionar con el marker de Mnemo)."""
    t = (text or "")[:limit]
    return t.replace("```", "ʼʼʼ").replace("<!--", "&lt;!--").replace("-->", "--&gt;")
```
y en `_self_heal_body`, sustituir cada `{payload.get('reasoning', '')}` por `{_sanitize_md(payload.get('reasoning', ''))}` (líneas ~18 y ~28).

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_ai_repair_actuator.py tests/test_actions_service.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/actions/ai_repair.py src/actions/service.py tests/test_ai_repair_actuator.py tests/test_actions_service.py
git commit -m "fix(actions): truncar el código del cliente al LLM (8000) + sanear el texto del LLM en el body

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: E-1 + S-3 — tracing off por defecto + cota de input

**Files:** Modify `.env.example`, `src/multitenant_models.py`; Test `tests/test_api_v2_defects_ask.py`.

- [ ] **Step 1: Write the failing test** — en `tests/test_api_v2_defects_ask.py`, añadir (mirror del patrón de overrides existente en ese archivo):

```python
def test_ask_rejects_overlong_question(client_and_mocks):
    client, _ = client_and_mocks
    r = client.post("/v2/defects/ask", json={"org_id": "o1", "question": "x" * 5000})
    assert r.status_code == 422   # Pydantic rechaza > max_length antes de tocar el repo
```

(Usa el `client_and_mocks` ya existente en el archivo.)

- [ ] **Step 2: Run, expect FAIL** — devuelve 200 (sin cota).

- [ ] **Step 3: Implement**.

En `src/multitenant_models.py`, `AskRequest` — añadir la cota (importar `Field` de pydantic si no está):
```python
class AskRequest(BaseModel):
    org_id: str
    question: str = Field(max_length=2000)
```

En `.env.example`, cambiar la línea 2:
```
LANGCHAIN_TRACING_V2=false
```
(mantener intacto el AVISO de la línea ~35).

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_api_v2_defects_ask.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add .env.example src/multitenant_models.py tests/test_api_v2_defects_ask.py
git commit -m "fix(security): tracing LangSmith off por defecto + cota de longitud en AskRequest

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **A-1 endurece 5 escrituras** (no 3): el vector real es `mark_materializing` sobre una acción ya aprobada. Lecturas intactas.
- **El parche del código (`new_block`) NO se sanea** — es código intencional que va al archivo vía `open_draft_pr`; lo que se sanea es el `reasoning` que va al markdown.
- **Fuera de alcance:** BH3 (RLS conductual + cobertura), H2, God-objects, Bloque C.
