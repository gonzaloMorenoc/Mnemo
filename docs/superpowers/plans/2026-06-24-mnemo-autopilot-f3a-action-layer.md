# Mnemo Autopilot — F3a: marco de acción + bandeja Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir los veredictos de triaje en **acciones propuestas** (Nivel 2) en una bandeja de aprobación, con los dos actuadores que no escriben en GitHub (cuarentena + ticket enriquecido) y `CodeHost` como stub.

**Architecture:** `src/actions/` (`base` con `Actuator`/`ActionProposal`/`CodeHost`/`NullCodeHost`; `quarantine`; `ticket` que reusa `RootCauseAnalyzer`; `service` que orquesta). Tabla `actions` (migración 010). Endpoints `POST /v2/actions/run/{id}/propose`, `GET /v2/actions`, `approve`/`reject`. La propuesta se dispara con un POST explícito (el ticket usa el LLM, fuera del camino crítico).

**Tech Stack:** Python 3.13, FastAPI, psycopg, pytest. Actuadores y servicio testeables sin BD/LLM/GitHub (mocks).

## Global Constraints

- `Actuator.propose(verdict: Dict, context: Dict) -> Optional[ActionProposal]` (uniforme). El `context` lo rellena el servicio con lo que cada actuador necesita (quarantine: `test_name`; ticket: `family`+`failures`).
- **Nivel 2 estricto:** toda acción nace `proposed`; **nada se materializa sin `approve`**. `NullCodeHost` NO escribe en ningún sitio externo (GitHub real = F3c).
- **Cuarentena SIEMPRE con ticket de deuda** (`payload.debt_ticket` no vacío) — cuarentena sin ticket = ocultar bugs.
- **Ticket** reutiliza `RootCauseAnalyzer` (inyectado; **no** se reimplementa root-cause), prefiere el `root_cause` ya guardado de la familia, y **degrada** (LLM caído → "root-cause no disponible"; nunca rompe).
- **`propose_actions` idempotente por run:** reemplaza solo las acciones `proposed` del run; **preserva** `approved`/`rejected`/`materialized` (no se destruyen decisiones humanas).
- Repo membership-gated (el pooler bypassa RLS); `save_actions` valida `run_id → org_id`. Mapeo categoría→actuador: `flaky→quarantine`, `real→ticket`, resto→`skipped`. Solo veredictos `status='resolved'`.
- typing.Optional/Dict/List (no PEP 604). Params `%s`. Endpoints `/v2`: 401/403/404/502/503. Commit `<type>: <description>`.

---

### Task 1: Migración `010_actions.sql`

**Files:**
- Create: `db/migrations/010_actions.sql`

**Interfaces:**
- Produces: tabla `public.actions` (con RLS).

- [ ] **Step 1: Escribir la migración** (calca el patrón RLS de `db/migrations/009_triage.sql`)

```sql
-- db/migrations/010_actions.sql
-- Mnemo Autopilot F3a: acciones propuestas (Nivel 2) sobre los veredictos de triaje.

create table if not exists public.actions (
    id uuid primary key default gen_random_uuid(),
    triage_verdict_id uuid not null references public.triage_verdicts (id) on delete cascade,
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    kind text not null check (kind in ('quarantine', 'ticket', 'self_heal')),
    payload jsonb,
    summary text,
    status text not null default 'proposed'
        check (status in ('proposed', 'approved', 'rejected', 'materialized')),
    artifact_ref text,
    approved_by uuid,
    approved_at timestamptz,
    reject_reason text,
    created_at timestamptz not null default now()
);

create index if not exists idx_actions_run on public.actions (run_id);
create index if not exists idx_actions_org_status on public.actions (org_id, status);

alter table public.actions enable row level security;
alter table public.actions force row level security;
drop policy if exists actions_member on public.actions;
create policy actions_member on public.actions for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert, update, delete on public.actions to authenticated;
```

- [ ] **Step 2: Aplicar**

Run: `export DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"') && psql "$DATABASE_URL" -f db/migrations/010_actions.sql`
Expected: `CREATE TABLE` / `CREATE INDEX` / `CREATE POLICY` / `GRANT` sin errores.

- [ ] **Step 3: Verificar**

Run: `psql "$DATABASE_URL" -c "\d public.actions"`
Expected: columnas + RLS forzado + policy `actions_member` + FKs `on delete cascade`.

- [ ] **Step 4: Commit**

```bash
git add db/migrations/010_actions.sql
git commit -m "feat: migración 010 (tabla actions, Nivel 2)"
```

---

### Task 2: `src/actions/base.py` — `ActionProposal` / `Actuator` / `CodeHost` / `NullCodeHost`

**Files:**
- Create: `src/actions/__init__.py` (vacío)
- Create: `src/actions/base.py`
- Test: `tests/test_actions_base.py`

**Interfaces:**
- Produces: `ActionProposal(kind, payload, summary)`; `Actuator` (Protocol `propose(verdict, context) -> Optional[ActionProposal]`); `CodeHost` (Protocol `create_issue`/`open_draft_pr`); `NullCodeHost`.

- [ ] **Step 1: Escribir el test**

```python
# tests/test_actions_base.py
from src.actions.base import ActionProposal, NullCodeHost


def test_action_proposal_holds_fields():
    p = ActionProposal(kind="ticket", payload={"title": "x"}, summary="s")
    assert p.kind == "ticket" and p.payload["title"] == "x" and p.summary == "s"


def test_null_codehost_returns_stub_refs_and_writes_nothing():
    ch = NullCodeHost()
    assert ch.create_issue(title="t", body="b", labels=["x"]).startswith("stub://")
    assert ch.open_draft_pr(title="t", body="b", patch="p").startswith("stub://")
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_actions_base.py -v`
Expected: FAIL — `ModuleNotFoundError: src.actions.base`.

- [ ] **Step 3: Implementar**

Crear `src/actions/__init__.py` vacío, y:
```python
# src/actions/base.py
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ActionProposal:
    kind: str                       # quarantine | ticket | self_heal
    payload: Dict[str, Any]
    summary: str


class Actuator(Protocol):
    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]: ...


class CodeHost(Protocol):
    def create_issue(self, *, title: str, body: str, labels: List[str]) -> str: ...
    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str: ...


class NullCodeHost:
    """Stub: NO escribe en ningún sitio externo; devuelve un ref placeholder.
    El CodeHost real (GitHub App) es F3c."""

    def create_issue(self, *, title: str, body: str, labels: List[str]) -> str:
        return "stub://issue/pending"

    def open_draft_pr(self, *, title: str, body: str, patch: str) -> str:
        return "stub://pr/pending"
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_actions_base.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/__init__.py src/actions/base.py tests/test_actions_base.py
git commit -m "feat(actions): base (ActionProposal, Actuator, CodeHost, NullCodeHost)"
```

---

### Task 3: `src/actions/quarantine.py` — `QuarantineActuator`

**Files:**
- Create: `src/actions/quarantine.py`
- Test: `tests/test_actions_quarantine.py`

**Interfaces:**
- Consumes: `ActionProposal` (Task 2).
- Produces: `QuarantineActuator` con `propose(verdict, context) -> ActionProposal` (flaky → cuarentena + ticket de deuda).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_actions_quarantine.py
from src.actions.quarantine import QuarantineActuator


def _verdict(**over):
    base = {"verdict_id": "v1", "category": "flaky", "confidence": 0.9,
            "evidence_bundle": {"family_id": "fam-1"}}
    base.update(over)
    return base


def test_quarantine_always_has_non_empty_debt_ticket():
    p = QuarantineActuator().propose(_verdict(), {"test_name": "t_login"})
    assert p.kind == "quarantine"
    dt = p.payload["debt_ticket"]
    assert dt["title"] and dt["body"]            # invariante: nunca vacío
    assert "t_login" in dt["title"] or "t_login" in dt["body"]


def test_quarantine_includes_annotation_with_test_name():
    p = QuarantineActuator().propose(_verdict(), {"test_name": "t_login"})
    assert p.payload["annotation"]["test_name"] == "t_login"
    assert "t_login" in p.summary


def test_quarantine_handles_missing_test_name():
    p = QuarantineActuator().propose(_verdict(), {})
    assert p.payload["debt_ticket"]["title"]     # sigue produciendo ticket de deuda
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_actions_quarantine.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
# src/actions/quarantine.py
from typing import Any, Dict, Optional

from src.actions.base import ActionProposal


class QuarantineActuator:
    """Flaky → cuarentena con deuda. Determinista (sin LLM). SIEMPRE ticket de deuda
    (cuarentena sin ticket = ocultar bugs)."""

    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]:
        test_name = context.get("test_name") or "(test desconocido)"
        ev = verdict.get("evidence_bundle") or {}
        family_id = ev.get("family_id")
        debt_ticket = {
            "title": f"[Flaky] {test_name}",
            "body": (
                f"El test `{test_name}` se clasificó como **flaky** "
                f"(confianza {verdict.get('confidence')}).\n\n"
                f"Familia de defecto: `{family_id}`.\n\n"
                "Puesto en cuarentena con **deuda abierta**: no se oculta el fallo, queda "
                "registrado para revisión. Quitar de cuarentena cuando el test se estabilice."
            ),
            "labels": ["flaky", "mnemo-debt"],
        }
        annotation = {
            "test_name": test_name,
            "suggestion": (
                f"Anotar `{test_name}` con `test.fixme()` o tag `@flaky` y un retry; "
                "mantener la deuda abierta hasta estabilizar."
            ),
        }
        return ActionProposal(
            kind="quarantine",
            payload={"debt_ticket": debt_ticket, "annotation": annotation},
            summary=f"Cuarentena + deuda: {test_name}",
        )
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_actions_quarantine.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/quarantine.py tests/test_actions_quarantine.py
git commit -m "feat(actions): QuarantineActuator (cuarentena + ticket de deuda)"
```

---

### Task 4: `src/actions/ticket.py` — `TicketActuator`

**Files:**
- Create: `src/actions/ticket.py`
- Test: `tests/test_actions_ticket.py`

**Interfaces:**
- Consumes: `ActionProposal` (Task 2); un analyzer con `.analyze(family, failures) -> str` (`RootCauseAnalyzer`).
- Produces: `TicketActuator(analyzer)` con `propose(verdict, context) -> ActionProposal` (real → ticket enriquecido; prefiere `family.root_cause`; degrada a None del LLM).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_actions_ticket.py
from unittest.mock import MagicMock

from src.actions.ticket import TicketActuator


def _verdict(**over):
    base = {"verdict_id": "v1", "category": "real", "confidence": 0.85,
            "rule_applied": "R4_real_recurrent",
            "evidence_bundle": {"family_id": "fam-1", "lineage_projects": ["web", "admin"]}}
    base.update(over)
    return base


def _ctx(root_cause=None):
    return {"test_name": "t_checkout",
            "family": {"title": "TimeoutError", "occurrence_count": 3, "root_cause": root_cause},
            "failures": [{"test_name": "t_checkout", "error_type": "TimeoutError",
                          "message": "boom", "trace": None, "project": "web"}]}


def test_ticket_uses_analyzer_when_no_stored_root_cause():
    analyzer = MagicMock()
    analyzer.analyze.return_value = "## Causa raíz\nProbable regresión."
    p = TicketActuator(analyzer).propose(_verdict(), _ctx())
    assert p.kind == "ticket"
    analyzer.analyze.assert_called_once()
    assert "Probable regresión" in p.payload["body"]
    assert "web, admin" in p.payload["body"]            # linaje


def test_ticket_prefers_stored_root_cause_no_llm_call():
    analyzer = MagicMock()
    p = TicketActuator(analyzer).propose(_verdict(), _ctx(root_cause="Ya analizado."))
    analyzer.analyze.assert_not_called()
    assert "Ya analizado." in p.payload["body"]


def test_ticket_degrades_when_analyzer_raises():
    analyzer = MagicMock()
    analyzer.analyze.side_effect = RuntimeError("LLM caído")
    p = TicketActuator(analyzer).propose(_verdict(), _ctx())
    assert "no disponible" in p.payload["body"].lower()
    assert p.kind == "ticket"
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_actions_ticket.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar**

```python
# src/actions/ticket.py
from typing import Any, Dict, Optional

from src.actions.base import ActionProposal


class TicketActuator:
    """Defecto real → ticket enriquecido: root-cause (RootCauseAnalyzer, inyectado) +
    linaje cross-proyecto + severidad. Prefiere el root_cause ya guardado; degrada a
    'no disponible' si el LLM falla (nunca rompe)."""

    def __init__(self, analyzer: Any):
        self._analyzer = analyzer

    def propose(
        self, verdict: Dict[str, Any], context: Dict[str, Any]
    ) -> Optional[ActionProposal]:
        ev = verdict.get("evidence_bundle") or {}
        test_name = context.get("test_name") or "(test desconocido)"
        lineage = ev.get("lineage_projects") or []
        family = context.get("family") or {}
        failures = context.get("failures") or []

        root_cause = family.get("root_cause")
        if not root_cause and failures:
            try:
                root_cause = self._analyzer.analyze(family, failures)
            except Exception:  # noqa: BLE001 — degrada; el ticket se propone igual
                root_cause = None

        lineage_line = (
            f"Esta familia ya apareció en: {', '.join(lineage)}." if lineage
            else "Primera aparición de esta familia."
        )
        body = (
            f"**Defecto real** en `{test_name}` "
            f"(confianza {verdict.get('confidence')}, regla {verdict.get('rule_applied')}).\n\n"
            f"{lineage_line}\n\n"
            "## Causa raíz (hipótesis)\n"
            f"{root_cause or '_root-cause no disponible (LLM no accesible)._'}\n"
        )
        return ActionProposal(
            kind="ticket",
            payload={"title": f"[Defecto] {test_name}", "body": body, "labels": ["bug", "mnemo"]},
            summary=f"Ticket de defecto real: {test_name}",
        )
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_actions_ticket.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/ticket.py tests/test_actions_ticket.py
git commit -m "feat(actions): TicketActuator (ticket enriquecido, reusa RootCauseAnalyzer)"
```

---

### Task 5: Repo — `get_run_actionable_verdicts` / `save_actions` / `get_actions` / `get_action` / `approve_action` / `reject_action`

**Files:**
- Modify: `src/defects/repository.py` (métodos al final de `AssuranceRepository`)
- Test: `tests/test_actions_repository.py` (integration)

**Interfaces:**
- Consumes: `_connect`/`_set_claims`/`Json`; tablas `triage_verdicts`/`failures`/`test_runs`/`actions` (migración 010).
- Produces:
  - `get_run_actionable_verdicts(*, user_id, run_id) -> List[Dict]` — veredictos `resolved` del run + datos del fallo (`test_name`, `error_type`, `defect_family_id`), membership-gated.
  - `save_actions(*, user_id, org_id, run_id, actions: List[Dict]) -> int` — borra solo las `proposed` del run y reinserta (preserva el resto); valida membership + `run_id → org_id`.
  - `get_actions(*, user_id, org_id, status=None) -> List[Dict]`; `get_action(*, user_id, action_id) -> Optional[Dict]`.
  - `approve_action(*, user_id, action_id, artifact_ref) -> bool` / `reject_action(*, user_id, action_id, reason) -> bool` (solo si `proposed`).

- [ ] **Step 1: Escribir los tests (integration)**

```python
# tests/test_actions_repository.py
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord

DBURL = os.getenv("DATABASE_URL", "")


def _emb(seed):
    return [seed] + [0.0] * 383


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org(repo):
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"test-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def _resolved_verdict(repo, u, o):
    """Ingiere un run con un fallo real y persiste un veredicto 'resolved'; devuelve (run_id, verdict_id, fid)."""
    rec = FailureRecord(test_name="t_checkout", error_type="AssertionError", message="boom",
                        trace=None, project="web", source="playwright")
    item = IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(1.0))
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="web", source="playwright", run_uid="ra",
                           items=[item], results=[{"test_name": "t_checkout", "status": "fail"}], snapshots=[])
    fid = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["failure_id"]
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[{
        "failure_id": fid, "category": "real", "confidence": 0.85, "rule_applied": "R4_real_recurrent",
        "evidence_bundle": {"family_id": "x"}, "requires_approval": False, "llm_assisted": False,
        "status": "resolved"}])
    vid = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])[0]["id"]
    return r["run_id"], vid, fid


def test_get_run_actionable_verdicts_joins_failure(repo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    rows = repo.get_run_actionable_verdicts(user_id=u, run_id=run_id)
    assert len(rows) == 1
    assert rows[0]["verdict_id"] == vid and rows[0]["test_name"] == "t_checkout"
    assert rows[0]["category"] == "real"
    # no-miembro → vacío
    assert repo.get_run_actionable_verdicts(user_id=str(uuid.uuid4()), run_id=run_id) == []


def test_save_get_approve_reject_roundtrip(repo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    n = repo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {"title": "T"}, "summary": "s"}])
    assert n == 1
    inbox = repo.get_actions(user_id=u, org_id=o, status="proposed")
    assert len(inbox) == 1 and inbox[0]["kind"] == "ticket"
    aid = inbox[0]["id"]
    assert repo.approve_action(user_id=u, action_id=aid, artifact_ref="stub://issue/1") is True
    got = repo.get_actions(user_id=u, org_id=o)[0]
    assert got["status"] == "approved" and got["artifact_ref"] == "stub://issue/1"
    assert got["approved_by"] == u
    # rechazar uno ya aprobado → False (solo se rechaza si proposed)
    assert repo.reject_action(user_id=u, action_id=aid, reason="x") is False


def test_save_actions_preserves_approved_on_reproposal(repo, org):
    u, o = org["user_id"], org["org_id"]
    run_id, vid, _ = _resolved_verdict(repo, u, o)
    repo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s"}])
    aid = repo.get_actions(user_id=u, org_id=o)[0]["id"]
    repo.approve_action(user_id=u, action_id=aid, artifact_ref="stub://issue/1")
    # re-proponer: la aprobada NO se borra
    repo.save_actions(user_id=u, org_id=o, run_id=run_id, actions=[
        {"triage_verdict_id": vid, "kind": "ticket", "payload": {}, "summary": "s2"}])
    all_actions = repo.get_actions(user_id=u, org_id=o)
    assert any(a["status"] == "approved" for a in all_actions)   # preservada
    assert any(a["status"] == "proposed" for a in all_actions)   # nueva propuesta


def test_save_actions_rejects_foreign_run(repo, org):
    u, o = org["user_id"], org["org_id"]
    with pytest.raises((ValueError, PermissionError)):
        repo.save_actions(user_id=u, org_id=o, run_id=str(uuid.uuid4()), actions=[])
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_actions_repository.py -v`
Expected: FAIL — `AttributeError: ... 'get_run_actionable_verdicts'`.

- [ ] **Step 3: Implementar** — añadir al final de `AssuranceRepository`

```python
    def get_run_actionable_verdicts(self, *, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        """Veredictos 'resolved' del run + datos del fallo (test_name, error_type, familia).
        Vacío si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select tv.id as verdict_id, tv.failure_id, tv.org_id, tv.category,"
                    "       tv.confidence, tv.requires_approval, tv.evidence_bundle,"
                    "       f.test_name, f.error_type, f.defect_family_id"
                    " from public.triage_verdicts tv"
                    " join public.test_runs r on r.id = tv.run_id"
                    " join public.failures f on f.id = tv.failure_id"
                    " where tv.run_id = %s and tv.status = 'resolved'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = r.org_id and m.user_id = %s)"
                    " order by tv.created_at",
                    (run_id, user_id),
                )
                return [
                    {"verdict_id": str(r["verdict_id"]), "failure_id": str(r["failure_id"]),
                     "org_id": str(r["org_id"]), "category": r["category"],
                     "confidence": r["confidence"], "requires_approval": r["requires_approval"],
                     "evidence_bundle": r["evidence_bundle"], "test_name": r["test_name"],
                     "error_type": r["error_type"],
                     "defect_family_id": str(r["defect_family_id"]) if r["defect_family_id"] else None}
                    for r in cur.fetchall()
                ]

    def save_actions(
        self, *, user_id: str, org_id: str, run_id: str, actions: List[Dict[str, Any]]
    ) -> int:
        """Reemplaza solo las acciones 'proposed' del run (preserva approved/rejected/
        materialized). Lanza PermissionError/ValueError si no es miembro / el run no es del org."""
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

    def _action_rows(self, cur) -> List[Dict[str, Any]]:
        return [
            {"id": str(r["id"]), "triage_verdict_id": str(r["triage_verdict_id"]),
             "run_id": str(r["run_id"]), "kind": r["kind"], "payload": r["payload"],
             "summary": r["summary"], "status": r["status"], "artifact_ref": r["artifact_ref"],
             "approved_by": str(r["approved_by"]) if r["approved_by"] else None,
             "approved_at": r["approved_at"].isoformat() if r["approved_at"] else None,
             "reject_reason": r["reject_reason"]}
            for r in cur.fetchall()
        ]

    def get_actions(
        self, *, user_id: str, org_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Bandeja de acciones del org (status opcional). Vacío si no es miembro."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute("select exists(select 1 from public.memberships"
                            " where org_id = %s and user_id = %s) as ok", (org_id, user_id))
                if not cur.fetchone()["ok"]:
                    return []
                cols = ("id, triage_verdict_id, run_id, kind, payload, summary, status,"
                        " artifact_ref, approved_by, approved_at, reject_reason")
                if status:
                    cur.execute(f"select {cols} from public.actions"
                                " where org_id = %s and status = %s order by created_at desc",
                                (org_id, status))
                else:
                    cur.execute(f"select {cols} from public.actions"
                                " where org_id = %s order by created_at desc", (org_id,))
                return self._action_rows(cur)

    def get_action(self, *, user_id: str, action_id: str) -> Optional[Dict[str, Any]]:
        """Una acción por id (membership-gated). None si no es miembro / no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select a.id, a.triage_verdict_id, a.run_id, a.kind, a.payload, a.summary,"
                    "       a.status, a.artifact_ref, a.approved_by, a.approved_at, a.reject_reason"
                    " from public.actions a"
                    " where a.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = a.org_id and m.user_id = %s)",
                    (action_id, user_id),
                )
                rows = self._action_rows(cur)
                return rows[0] if rows else None

    def approve_action(self, *, user_id: str, action_id: str, artifact_ref: str) -> bool:
        """Aprueba (solo si 'proposed'): status='approved' + sign-off + ref. Membership-gated."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.actions a set status = 'approved', artifact_ref = %s,"
                    "  approved_by = %s, approved_at = now()"
                    " where a.id = %s and a.status = 'proposed'"
                    "   and exists (select 1 from public.memberships m"
                    "     where m.org_id = a.org_id and m.user_id = %s)",
                    (artifact_ref, user_id, action_id, user_id),
                )
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def reject_action(self, *, user_id: str, action_id: str, reason: str) -> bool:
        """Rechaza (solo si 'proposed'): status='rejected' + motivo. Membership-gated."""
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

(Confirmar que `Optional` está importado de `typing` en `repository.py`; si falta, añadirlo.)

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_actions_repository.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_actions_repository.py
git commit -m "feat(actions): repo (verdicts accionables + CRUD de acciones, idempotente y aislado)"
```

---

### Task 6: `src/actions/service.py` — `ActionService`

**Files:**
- Create: `src/actions/service.py`
- Test: `tests/test_actions_service.py`

**Interfaces:**
- Consumes: `NullCodeHost` (Task 2); el repo (Task 5: `get_run_actionable_verdicts`, `get_family_with_failures`, `save_actions`, `get_action`, `approve_action`, `reject_action`); los actuadores (Tasks 3-4).
- Produces: `ActionService(*, repo, actuators: Dict[str, Actuator], codehost=NullCodeHost())` con `propose_actions(*, user_id, run_id) -> Dict[str,int]`, `approve_action(*, user_id, action_id) -> Dict`, `reject_action(*, user_id, action_id, reason="") -> bool`.

- [ ] **Step 1: Escribir los tests (repo + actuadores + codehost mockeados)**

```python
# tests/test_actions_service.py
from unittest.mock import MagicMock

from src.actions.base import ActionProposal
from src.actions.service import ActionService


def _svc(verdicts):
    repo = MagicMock()
    repo.get_run_actionable_verdicts.return_value = verdicts
    repo.get_family_with_failures.return_value = {"family": {"title": "F"}, "failures": [{"x": 1}]}
    repo.save_actions.return_value = len(verdicts)
    quarantine = MagicMock()
    quarantine.propose.return_value = ActionProposal("quarantine", {"debt_ticket": {"title": "t"}}, "q")
    ticket = MagicMock()
    ticket.propose.return_value = ActionProposal("ticket", {"title": "t"}, "tk")
    svc = ActionService(repo=repo, actuators={"flaky": quarantine, "real": ticket})
    return svc, repo, quarantine, ticket


def test_propose_maps_categories_and_skips_unmapped():
    verdicts = [
        {"verdict_id": "v1", "category": "flaky", "org_id": "o", "evidence_bundle": {}, "test_name": "a"},
        {"verdict_id": "v2", "category": "real", "org_id": "o", "evidence_bundle": {}, "test_name": "b",
         "defect_family_id": "fam"},
        {"verdict_id": "v3", "category": "maintenance", "org_id": "o", "evidence_bundle": {}, "test_name": "c"},
    ]
    svc, repo, quarantine, ticket = _svc(verdicts)
    counts = svc.propose_actions(user_id="u", run_id="r")
    assert counts == {"quarantine": 1, "ticket": 1, "skipped": 1}
    # el ticket recibió context con family+failures (fetch de get_family_with_failures)
    _, ctx = ticket.propose.call_args.args
    assert ctx["family"]["title"] == "F" and ctx["test_name"] == "b"
    # quarantine recibió test_name pero NO se le buscó familia
    repo.get_family_with_failures.assert_called_once()   # solo para el 'real'
    repo.save_actions.assert_called_once()
    saved = repo.save_actions.call_args.kwargs["actions"]
    assert {a["kind"] for a in saved} == {"quarantine", "ticket"}


def test_propose_no_actionable_does_not_save():
    svc, repo, _, _ = _svc([])
    assert svc.propose_actions(user_id="u", run_id="r") == {"quarantine": 0, "ticket": 0, "skipped": 0}
    repo.save_actions.assert_not_called()


def test_approve_materializes_via_codehost_and_records_ref():
    repo = MagicMock()
    repo.get_action.return_value = {"id": "a1", "kind": "ticket",
                                    "payload": {"title": "T", "body": "B", "labels": ["bug"]}}
    repo.approve_action.return_value = True
    codehost = MagicMock()
    codehost.create_issue.return_value = "stub://issue/9"
    svc = ActionService(repo=repo, actuators={}, codehost=codehost)
    out = svc.approve_action(user_id="u", action_id="a1")
    assert out == {"approved": True, "artifact_ref": "stub://issue/9"}
    codehost.create_issue.assert_called_once()
    assert repo.approve_action.call_args.kwargs["artifact_ref"] == "stub://issue/9"


def test_reject_delegates_to_repo():
    repo = MagicMock()
    repo.reject_action.return_value = True
    svc = ActionService(repo=repo, actuators={})
    assert svc.reject_action(user_id="u", action_id="a1", reason="dup") is True
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_actions_service.py -v`
Expected: FAIL — `ModuleNotFoundError: src.actions.service`.

- [ ] **Step 3: Implementar**

```python
# src/actions/service.py
from typing import Any, Dict, Optional

from src.actions.base import Actuator, CodeHost, NullCodeHost

_CATEGORIES = ("quarantine", "ticket")


class ActionService:
    """Orquesta la capa de acción: de los veredictos resueltos genera acciones propuestas,
    y materializa/rechaza al aprobar. Nivel 2: nada externo sin approve."""

    def __init__(
        self, *, repo, actuators: Dict[str, Actuator], codehost: Optional[CodeHost] = None
    ):
        self.repo = repo
        self.actuators = actuators
        self.codehost = codehost or NullCodeHost()

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
            self.repo.save_actions(user_id=user_id, org_id=org_id, run_id=run_id, actions=proposals)
        return counts

    def _context_for(self, user_id: str, verdict: Dict[str, Any]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"test_name": verdict.get("test_name")}
        if verdict["category"] == "real" and verdict.get("defect_family_id"):
            fam = self.repo.get_family_with_failures(
                user_id=user_id, defect_id=verdict["defect_family_id"]
            )
            if fam:
                ctx["family"] = fam.get("family") or {}
                ctx["failures"] = fam.get("failures") or []
        return ctx

    def approve_action(self, *, user_id: str, action_id: str) -> Dict[str, Any]:
        action = self.repo.get_action(user_id=user_id, action_id=action_id)
        if action is None:
            return {"approved": False, "artifact_ref": None}
        ref = self._materialize(action)
        ok = self.repo.approve_action(user_id=user_id, action_id=action_id, artifact_ref=ref)
        return {"approved": ok, "artifact_ref": ref}

    def _materialize(self, action: Dict[str, Any]) -> str:
        payload = action.get("payload") or {}
        if action["kind"] == "ticket":
            return self.codehost.create_issue(
                title=payload.get("title", ""), body=payload.get("body", ""),
                labels=payload.get("labels", []),
            )
        if action["kind"] == "quarantine":
            dt = payload.get("debt_ticket") or {}
            return self.codehost.create_issue(
                title=dt.get("title", ""), body=dt.get("body", ""), labels=dt.get("labels", []),
            )
        return "stub://unknown"

    def reject_action(self, *, user_id: str, action_id: str, reason: str = "") -> bool:
        return self.repo.reject_action(user_id=user_id, action_id=action_id, reason=reason)
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_actions_service.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/actions/service.py tests/test_actions_service.py
git commit -m "feat(actions): ActionService (propose/approve/reject)"
```

---

### Task 7: Endpoints `/v2/actions*` + wiring

**Files:**
- Modify: `src/multitenant_models.py` (modelos `ActionResponse`, `ActionRejectRequest`, `ProposeActionsResponse`)
- Modify: `src/api_v2.py` (singleton `get_action_service` + 4 endpoints)
- Test: `tests/test_api_v2_actions.py` (nuevo)

**Interfaces:**
- Consumes: `ActionService` (Task 6), `QuarantineActuator`/`TicketActuator` (Tasks 3-4), `get_root_cause_analyzer`/`get_assurance_repo`/`get_current_user` (existentes).
- Produces: `POST /v2/actions/run/{run_id}/propose`, `GET /v2/actions`, `POST /v2/actions/{action_id}/approve`, `POST /v2/actions/{action_id}/reject`.

- [ ] **Step 1: Escribir los tests (`tests/test_api_v2_actions.py`)**

```python
import psycopg
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, repo=None, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if service is not None:
        app.dependency_overrides[api_v2.get_action_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_propose_returns_counts():
    svc = MagicMock()
    svc.propose_actions.return_value = {"quarantine": 1, "ticket": 2, "skipped": 0}
    resp = _client(service=svc).post("/v2/actions/run/r1/propose")
    assert resp.status_code == 200
    assert resp.json() == {"quarantine": 1, "ticket": 2, "skipped": 0}
    svc.propose_actions.assert_called_once_with(user_id="user-1", run_id="r1")


def test_inbox_returns_actions():
    repo = MagicMock()
    repo.get_actions.return_value = [{"id": "a1", "triage_verdict_id": "v1", "run_id": "r1",
        "kind": "ticket", "payload": {"title": "T"}, "summary": "s", "status": "proposed",
        "artifact_ref": None, "approved_by": None, "approved_at": None, "reject_reason": None}]
    resp = _client(repo=repo).get("/v2/actions?org_id=o1&status=proposed")
    assert resp.status_code == 200 and resp.json()[0]["kind"] == "ticket"
    repo.get_actions.assert_called_once_with(user_id="user-1", org_id="o1", status="proposed")


def test_approve_and_reject():
    svc = MagicMock()
    svc.approve_action.return_value = {"approved": True, "artifact_ref": "stub://issue/1"}
    svc.reject_action.return_value = True
    client = _client(service=svc)
    assert client.post("/v2/actions/a1/approve").json()["approved"] is True
    assert client.post("/v2/actions/a1/reject", json={"reason": "dup"}).status_code == 200
    svc.reject_action.assert_called_once_with(user_id="user-1", action_id="a1", reason="dup")


def test_propose_requires_auth():
    assert _client(service=MagicMock(), with_user=False).post("/v2/actions/run/r1/propose").status_code == 401


def test_inbox_db_error_is_502():
    repo = MagicMock()
    repo.get_actions.side_effect = psycopg.OperationalError("db")
    assert _client(repo=repo).get("/v2/actions?org_id=o1").status_code == 502
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_api_v2_actions.py -v`
Expected: FAIL — `get_action_service` / rutas no existen.

- [ ] **Step 3: Añadir los modelos** en `src/multitenant_models.py`

```python
class ProposeActionsResponse(BaseModel):
    quarantine: int = 0
    ticket: int = 0
    skipped: int = 0


class ActionResponse(BaseModel):
    id: str
    triage_verdict_id: str
    run_id: str
    kind: str
    payload: Optional[dict] = None
    summary: Optional[str] = None
    status: str
    artifact_ref: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    reject_reason: Optional[str] = None


class ActionRejectRequest(BaseModel):
    reason: str = ""
```

- [ ] **Step 4: Wiring en `src/api_v2.py`**

Imports:
```python
from src.actions.quarantine import QuarantineActuator
from src.actions.service import ActionService
from src.actions.ticket import TicketActuator
```
Añadir `ActionResponse, ActionRejectRequest, ProposeActionsResponse` a la importación de `src.multitenant_models`.

Singleton (tras `get_triage_service`):
```python
_action_service = None


def get_action_service() -> ActionService:
    if not multi_tenant_enabled():
        raise HTTPException(status_code=503, detail="Multi-tenant KB not configured")
    global _action_service
    if _action_service is None:
        _action_service = ActionService(
            repo=get_assurance_repo(),
            actuators={"flaky": QuarantineActuator(), "real": TicketActuator(get_root_cause_analyzer())},
        )
    return _action_service
```

Endpoints (tras los de triaje):
```python
@router.post("/actions/run/{run_id}/propose", response_model=ProposeActionsResponse)
def propose_actions_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> ProposeActionsResponse:
    try:
        return ProposeActionsResponse(**service.propose_actions(user_id=user.user_id, run_id=run_id))
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.get("/actions", response_model=List[ActionResponse])
def list_actions_v2(
    org_id: str,
    status: Optional[str] = None,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
) -> List[ActionResponse]:
    try:
        rows = repo.get_actions(user_id=user.user_id, org_id=org_id, status=status)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return [ActionResponse(**r) for r in rows]


@router.post("/actions/{action_id}/approve")
def approve_action_v2(
    action_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> Dict[str, Any]:
    try:
        return service.approve_action(user_id=user.user_id, action_id=action_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc


@router.post("/actions/{action_id}/reject")
def reject_action_v2(
    action_id: str,
    body: ActionRejectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service: ActionService = Depends(get_action_service),
) -> Dict[str, bool]:
    try:
        ok = service.reject_action(user_id=user.user_id, action_id=action_id, reason=body.reason)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    return {"rejected": ok}
```

(Confirmar que `Dict`, `Any`, `List`, `Optional` están importados de `typing` en `api_v2.py`; si falta alguno, añadirlo.)

- [ ] **Step 5: Ejecutar (pasa) + suite completa**

Run: `pytest tests/test_api_v2_actions.py -v && pytest -m "not integration" -q`
Expected: endpoints PASS; suite unitaria completa verde (sin regresiones).

- [ ] **Step 6: Commit**

```bash
git add src/api_v2.py src/multitenant_models.py tests/test_api_v2_actions.py
git commit -m "feat(actions): endpoints /v2/actions (propose/inbox/approve/reject)"
```

---

## Self-Review

**1. Cobertura del spec (F3a):**
- Marco `Actuator`/`ActionProposal`/`CodeHost`/`NullCodeHost` → Task 2. ✓
- Cuarentena (ticket de deuda SIEMPRE + anotación) → Task 3. ✓
- Ticket enriquecido (reusa `RootCauseAnalyzer` + linaje, degrada, prefiere root_cause guardado) → Task 4. ✓
- Tabla `actions` (010, RLS) → Task 1. Repo (verdicts accionables + CRUD, idempotente que preserva aprobadas, aislado) → Task 5. ✓
- `ActionService` (propose POST explícito, mapeo categoría→actuador, approve materializa vía CodeHost stub, reject) → Task 6. ✓
- Endpoints propose/inbox/approve/reject → Task 7. ✓

**2. Placeholders:** ninguno; código/SQL completo + comandos con salida esperada.

**3. Consistencia de tipos:** `Actuator.propose(verdict, context)` (T2) lo implementan T3/T4 y lo llama `ActionService` (T6) con el `context` que arma desde `get_run_actionable_verdicts`+`get_family_with_failures` (T5); `ActionProposal.kind/payload/summary` fluye a `save_actions` (T5) y a `ActionResponse` (T7); `approve_action` del servicio (T6) materializa vía `CodeHost.create_issue` (T2) y persiste con `repo.approve_action(artifact_ref)` (T5). `NullCodeHost` no escribe nada externo. `get_family_with_failures` devuelve `{"family":{...root_cause...},"failures":[...]}` (verificado) → encaja con `analyzer.analyze(family, failures)`.

**Nota:** `repository.py` sigue creciendo; F3a añade 6 métodos. Considerar extraer un `ActionRepository`/`TriageRepository` cuando se aborde F3b/F3c (no en F3a).

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-24-mnemo-autopilot-f3a-action-layer.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> Rama `feat/mnemo-actions` (nueva, sobre `main`). Tasks 1 y 5 tocan la BD (migración 010 + tests integration); 2/3/4/6/7 son testeables sin BD/LLM/GitHub (mocks). Tras F3a: **F3b** (self-heal del locator: candidatos DOM + diff LLM) y **F3c** (GitHub App: PR/Issue reales al aprobar).
