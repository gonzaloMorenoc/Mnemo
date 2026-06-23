# Mnemo Autopilot — F2d: repositorio del triaje Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La capa de repositorio que **conecta el motor de triaje (F2b/c) a los datos**: recupera de Postgres, por cada fallo de un run, los hechos que alimentan `FailureInput` (is_novel, family_label, retry_passed_in_run, intermittent_same_sha, has_green_baseline, dom_changed) y **persiste los `triage_verdicts`**.

**Architecture:** Migración `009_triage` (tabla `triage_verdicts` + `defect_families.label`). Una función pura `normalize_dom`/`dom_changed` para la señal de DOM. Métodos nuevos en `AssuranceRepository`: `get_triage_inputs` (ensambla los hechos por fallo con queries set-based), `save_triage_verdicts` (reemplaza por run → idempotente), `get_triage_for_run`, `set_family_label`. `mass_cofailure` NO se calcula aquí (depende de `classify_error`, lo hace el servicio en F2e).

**Tech Stack:** Python 3.13, psycopg (dict_row), Postgres (Supabase), pytest.

## Global Constraints

- Aislamiento multitenant: el pooler hace **BYPASS de RLS** → el aislamiento real es el **chequeo de membership en la capa de aplicación**. Todos los métodos nuevos lo aplican. NUNCA quitarlo.
- **`get_triage_inputs` NO calcula `mass_cofailure`** (depende de `classify_error`, lógica de F2bc; lo hace el servicio en F2e). Devuelve el resto de hechos + contexto del run.
- **`save_triage_verdicts` es idempotente**: reemplaza (delete+insert) los veredictos del run, de modo que re-triar no duplica filas.
- Migración siguiente libre: **009** (008 ya existe). RLS espejo de `002` (`enable`+`force` + policy `is_org_member` + grants a `authenticated`).
- Categorías válidas: `flaky|infra|maintenance|real|unknown`. Labels: `flaky|real|maintenance|infra|unknown`. Status veredicto: `resolved|needs_tiebreak`.
- Tests de repositorio = `integration` (Postgres con migración 009 aplicada; `DATABASE_URL` en `.env`, `load_dotenv`). `normalize_dom` es puro (unit). Params `%s` (no f-strings). Commit `<type>: <description>`.

---

### Task 1: Migración 009 — `triage_verdicts` + `defect_families.label`

**Files:**
- Create: `db/migrations/009_triage.sql`

**Interfaces:**
- Produces: tabla `public.triage_verdicts` (con RLS) y columna `public.defect_families.label`.

- [ ] **Step 1: Escribir la migración** (calca el patrón RLS de `db/migrations/002_assurance.sql`)

```sql
-- db/migrations/009_triage.sql
-- Mnemo Autopilot F2d: persistencia de veredictos de triaje + etiqueta de familia.

alter table public.defect_families
    add column if not exists label text not null default 'unknown'
    check (label in ('flaky', 'real', 'maintenance', 'infra', 'unknown'));

create table if not exists public.triage_verdicts (
    id uuid primary key default gen_random_uuid(),
    failure_id uuid not null references public.failures (id) on delete cascade,
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    category text not null check (category in ('flaky', 'infra', 'maintenance', 'real', 'unknown')),
    confidence real not null,
    rule_applied text not null,
    evidence_bundle jsonb,
    requires_approval boolean not null default false,
    llm_assisted boolean not null default false,
    status text not null default 'resolved' check (status in ('resolved', 'needs_tiebreak')),
    created_at timestamptz not null default now()
);

create index if not exists idx_triage_verdicts_run on public.triage_verdicts (run_id);
create index if not exists idx_triage_verdicts_org on public.triage_verdicts (org_id);

alter table public.triage_verdicts enable row level security;
alter table public.triage_verdicts force row level security;
drop policy if exists triage_verdicts_member on public.triage_verdicts;
create policy triage_verdicts_member on public.triage_verdicts for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
grant select, insert, update, delete on public.triage_verdicts to authenticated;
```

- [ ] **Step 2: Aplicar**

Run: `export DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"') && psql "$DATABASE_URL" -f db/migrations/009_triage.sql`
Expected: `ALTER TABLE` / `CREATE TABLE` / `CREATE INDEX` / `CREATE POLICY` / `GRANT` sin errores.

- [ ] **Step 3: Verificar**

Run: `psql "$DATABASE_URL" -c "\d public.triage_verdicts" -c "\d public.defect_families"`
Expected: `triage_verdicts` con sus columnas + RLS forzado + policy; `defect_families` incluye `label` con su CHECK.

- [ ] **Step 4: Commit**

```bash
git add db/migrations/009_triage.sql
git commit -m "feat: migración 009 (triage_verdicts + defect_families.label)"
```

---

### Task 2: `normalize_dom` / `dom_changed` (puro)

**Files:**
- Create: `src/triage/dom.py`
- Test: `tests/test_triage_dom.py`

**Interfaces:**
- Produces: `normalize_dom(html: str) -> str` (colapsa espacios + strip); `dom_changed(failure_html, green_html) -> bool` (False si falta alguno).

- [ ] **Step 1: Escribir los tests**

```python
# tests/test_triage_dom.py
from src.triage.dom import dom_changed, normalize_dom


def test_normalize_collapses_whitespace():
    assert normalize_dom("<a>  x\n\t y </a>") == "<a> x y </a>"
    assert normalize_dom("") == ""


def test_dom_changed_true_when_normalized_differs():
    assert dom_changed("<a>x</a>", "<a>y</a>") is True


def test_dom_changed_false_when_normalized_equal():
    # difieren solo en espacios → iguales tras normalizar
    assert dom_changed("<a>x</a>", "<a>   x  </a>") is False


def test_dom_changed_false_when_missing_either_side():
    assert dom_changed(None, "<a>x</a>") is False
    assert dom_changed("<a>x</a>", None) is False
    assert dom_changed("", "<a>x</a>") is False
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_dom.py -v`
Expected: FAIL — `ModuleNotFoundError: src.triage.dom`.

- [ ] **Step 3: Implementar**

```python
# src/triage/dom.py
import re
from typing import Optional

_WS = re.compile(r"\s+")


def normalize_dom(html: str) -> str:
    """Normaliza un DOM para comparar de forma robusta: colapsa secuencias de
    espacios en blanco a un solo espacio y recorta los extremos. Coarse pero
    suficiente para la señal 'DOM cambió' (el diff a nivel de elemento es F3)."""
    return _WS.sub(" ", html or "").strip()


def dom_changed(failure_html: Optional[str], green_html: Optional[str]) -> bool:
    """True si el DOM de fallo difiere (normalizado) del último verde. Si falta
    cualquiera de los dos, no hay señal de cambio → False."""
    if not failure_html or not green_html:
        return False
    return normalize_dom(failure_html) != normalize_dom(green_html)
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_dom.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/triage/dom.py tests/test_triage_dom.py
git commit -m "feat(triage): normalize_dom / dom_changed (puro)"
```

---

### Task 3: `AssuranceRepository.get_triage_inputs` — ensamblado de señales por fallo

**Files:**
- Modify: `src/defects/repository.py` (añadir el método; importar `dom_changed`)
- Test: `tests/test_triage_repository.py` (integration)

**Interfaces:**
- Consumes: `dom_changed` (Task 2); `_connect`/`_set_claims`; tablas `failures`/`defect_families`/`test_results`/`dom_snapshots`/`test_runs`.
- Produces: `get_triage_inputs(*, user_id: str, run_id: str) -> Dict[str, Any]` → `{"run": {id,org_id,project,commit_sha} | None, "failures": [ {failure_id, fingerprint, family_id, lineage_projects, error_type, message, trace, is_novel, family_label, retry_passed_in_run, intermittent_same_sha, has_green_baseline, dom_changed} ]}`. `None` si no es miembro / no existe el run.

- [ ] **Step 1: Escribir los tests (integration, una señal por test)**

```python
# tests/test_triage_repository.py
import os
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem
from src.ingest.models import FailureRecord

DBURL = os.getenv("DATABASE_URL", "")


def _emb(seed: float):
    return [seed] + [0.0] * 383


@pytest.fixture
def repo():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    return AssuranceRepository(DBURL)


@pytest.fixture
def org(repo):
    user_id = str(uuid.uuid4())
    email = f"test-{user_id[:8]}@test.internal"
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into auth.users (id, email, role, aud, created_at, updated_at)"
                " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                (user_id, email),
            )
            cur.execute(
                "insert into public.organizations (name, created_by) values (%s, %s) returning id",
                ("test-org-" + user_id[:8], user_id),
            )
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id = %s", (org_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))
        conn.commit()


def _item(test_name, msg, seed, error_type="TimeoutError"):
    rec = FailureRecord(test_name=test_name, error_type=error_type, message=msg,
                        trace=None, project="p", source="playwright")
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_get_triage_inputs_non_member(repo, org):
    out = repo.ingest_ci_run(user_id=org["user_id"], org_id=org["org_id"], project="p",
                             source="playwright", run_uid="r", items=[_item("t", "x", 1.0)],
                             results=[{"test_name": "t", "status": "fail"}], snapshots=[])
    other = str(uuid.uuid4())
    assert repo.get_triage_inputs(user_id=other, run_id=out["run_id"])["run"] is None


def test_is_novel_vs_recurrent(repo, org):
    u, o = org["user_id"], org["org_id"]
    # run 1: familia nueva
    r1 = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="n1",
                            items=[_item("t1", "TimeoutError boom", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out1 = repo.get_triage_inputs(user_id=u, run_id=r1["run_id"])
    assert out1["failures"][0]["is_novel"] is True
    # run 2: mismo error (misma familia) → ahora recurrente
    r2 = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="n2",
                            items=[_item("t1", "TimeoutError boom again", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out2 = repo.get_triage_inputs(user_id=u, run_id=r2["run_id"])
    assert out2["failures"][0]["is_novel"] is False


def test_retry_passed_and_family_label(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="rp",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "flaky", "retried": True}],
                           snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    f = out["failures"][0]
    assert f["retry_passed_in_run"] is True
    assert f["family_label"] == "unknown"  # default


def test_intermittent_same_sha(repo, org):
    u, o = org["user_id"], org["org_id"]
    # run A (commit sha1): el test pasa
    repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="a",
                       commit_sha="sha1", items=[],
                       results=[{"test_name": "t1", "status": "pass"}], snapshots=[])
    # run B (mismo sha1): el test falla
    rb = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="b",
                            commit_sha="sha1", items=[_item("t1", "TimeoutError x", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=rb["run_id"])
    assert out["failures"][0]["intermittent_same_sha"] is True


def test_has_green_baseline_and_dom_changed(repo, org):
    u, o = org["user_id"], org["org_id"]
    # run verde previo con baseline DOM
    repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="g",
                       commit_sha="sha2", items=[],
                       results=[{"test_name": "t1", "status": "pass"}],
                       snapshots=[{"test_name": "t1", "kind": "last_green",
                                   "content": "<html><button id='x'>Go</button></html>", "commit_sha": "sha2"}])
    # run con fallo y DOM distinto
    rf = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="f",
                            commit_sha="sha3", items=[_item("t1", "TimeoutError x", 1.0)],
                            results=[{"test_name": "t1", "status": "fail"}],
                            snapshots=[{"test_name": "t1", "kind": "failure",
                                        "content": "<html><button id='y'>Go</button></html>", "commit_sha": "sha3"}])
    out = repo.get_triage_inputs(user_id=u, run_id=rf["run_id"])
    f = out["failures"][0]
    assert f["has_green_baseline"] is True
    assert f["dom_changed"] is True
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_repository.py -v`
Expected: FAIL — `AttributeError: 'AssuranceRepository' object has no attribute 'get_triage_inputs'`.

- [ ] **Step 3: Implementar** — añadir el import y el método en `src/defects/repository.py`

En la cabecera de imports, añadir:
```python
from src.triage.dom import dom_changed
```

Añadir el método (al final de la clase `AssuranceRepository`):
```python
    def get_triage_inputs(self, *, user_id: str, run_id: str) -> Dict[str, Any]:
        """Recupera, por cada fallo de un run, los hechos para el triaje (is_novel,
        family_label, retry_passed_in_run, intermittent_same_sha, has_green_baseline,
        dom_changed) + el contexto del run. mass_cofailure NO se calcula aquí (depende
        de classify_error → lo hace el servicio en F2e). None si no es miembro/no existe."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select r.id, r.org_id, r.project, r.commit_sha from public.test_runs r"
                    " where r.id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)",
                    (run_id, user_id),
                )
                run = cur.fetchone()
                if run is None:
                    return {"run": None, "failures": []}
                org_id, project, commit_sha = run["org_id"], run["project"], run["commit_sha"]

                cur.execute(
                    "select f.id as failure_id, f.test_name, f.error_type, f.message, f.trace,"
                    "       f.fingerprint, f.defect_family_id, df.label as family_label"
                    " from public.failures f"
                    " left join public.defect_families df on df.id = f.defect_family_id"
                    " where f.run_id = %s",
                    (run_id,),
                )
                failures = cur.fetchall()
                family_ids = [f["defect_family_id"] for f in failures if f["defect_family_id"]]

                recurrent = set()
                lineage: Dict[Any, list] = {}
                if family_ids:
                    cur.execute(
                        "select distinct defect_family_id from public.failures"
                        " where defect_family_id = any(%s) and run_id <> %s",
                        (family_ids, run_id),
                    )
                    recurrent = {r["defect_family_id"] for r in cur.fetchall()}
                    cur.execute(
                        "select fl.defect_family_id as fid,"
                        "       array_agg(distinct r2.project) as projects"
                        " from public.failures fl join public.test_runs r2 on r2.id = fl.run_id"
                        " where fl.defect_family_id = any(%s) group by fl.defect_family_id",
                        (family_ids,),
                    )
                    lineage = {r["fid"]: list(r["projects"]) for r in cur.fetchall()}

                cur.execute(
                    "select distinct test_name from public.test_results"
                    " where run_id = %s and (status = 'flaky' or (status = 'pass' and retried))",
                    (run_id,),
                )
                retry_passed = {r["test_name"] for r in cur.fetchall()}

                intermittent = set()
                if commit_sha:
                    cur.execute(
                        "select tr.test_name from public.test_results tr"
                        " join public.test_runs r2 on r2.id = tr.run_id"
                        " where r2.org_id = %s and r2.commit_sha = %s"
                        " group by tr.test_name"
                        " having bool_or(tr.status = 'pass')"
                        "    and bool_or(tr.status in ('fail', 'flaky'))",
                        (org_id, commit_sha),
                    )
                    intermittent = {r["test_name"] for r in cur.fetchall()}

                cur.execute(
                    "select distinct on (test_name) test_name, content from public.dom_snapshots"
                    " where org_id = %s and project = %s and kind = 'last_green'"
                    " order by test_name, created_at desc",
                    (org_id, project),
                )
                green = {r["test_name"]: r["content"] for r in cur.fetchall()}
                cur.execute(
                    "select distinct on (test_name) test_name, content from public.dom_snapshots"
                    " where org_id = %s and project = %s and kind = 'failure'"
                    "   and commit_sha is not distinct from %s"
                    " order by test_name, created_at desc",
                    (org_id, project, commit_sha),
                )
                fail_dom = {r["test_name"]: r["content"] for r in cur.fetchall()}

            out = []
            for f in failures:
                fam = f["defect_family_id"]
                tn = f["test_name"]
                out.append({
                    "failure_id": str(f["failure_id"]),
                    "fingerprint": f["fingerprint"],
                    "family_id": str(fam) if fam else None,
                    "lineage_projects": lineage.get(fam, []),
                    "error_type": f["error_type"],
                    "message": f["message"],
                    "trace": f["trace"],
                    "is_novel": (fam not in recurrent) if fam else True,
                    "family_label": f["family_label"] or "unknown",
                    "retry_passed_in_run": tn in retry_passed,
                    "intermittent_same_sha": tn in intermittent,
                    "has_green_baseline": tn in green,
                    "dom_changed": dom_changed(fail_dom.get(tn), green.get(tn)),
                })
        return {
            "run": {"id": str(run["id"]), "org_id": str(org_id),
                    "project": project, "commit_sha": commit_sha},
            "failures": out,
        }
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_triage_repository.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_triage_repository.py
git commit -m "feat(triage): get_triage_inputs (ensamblado de señales por fallo)"
```

---

### Task 4: persistencia — `save_triage_verdicts` / `get_triage_for_run` / `set_family_label`

**Files:**
- Modify: `src/defects/repository.py` (3 métodos al final de la clase)
- Test: `tests/test_triage_repository.py` (integration; añadir)

**Interfaces:**
- Consumes: `_connect`/`_set_claims`/`Json`.
- Produces:
  - `save_triage_verdicts(*, user_id, org_id, run_id, verdicts: List[Dict]) -> int` — reemplaza los del run (idempotente). Cada verdict: `failure_id, category, confidence, rule_applied, evidence_bundle, requires_approval, llm_assisted, status?`.
  - `get_triage_for_run(*, user_id, run_id) -> List[Dict]`.
  - `set_family_label(*, user_id, family_id, label) -> bool` (ValueError si label inválido).

- [ ] **Step 1: Escribir los tests (integration; añadir a `tests/test_triage_repository.py`)**

```python
def _verdict(failure_id, category="real", conf=0.85):
    return {"failure_id": failure_id, "category": category, "confidence": conf,
            "rule_applied": "R4_real_recurrent", "evidence_bundle": {"k": "v"},
            "requires_approval": False, "llm_assisted": False, "status": "resolved"}


def test_save_and_get_triage_verdicts_idempotent(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="v",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    fid = out["failures"][0]["failure_id"]
    n = repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[_verdict(fid)])
    assert n == 1
    # re-guardar (idempotente) → sigue habiendo 1, no 2
    repo.save_triage_verdicts(user_id=u, org_id=o, run_id=r["run_id"], verdicts=[_verdict(fid, conf=0.9)])
    got = repo.get_triage_for_run(user_id=u, run_id=r["run_id"])
    assert len(got) == 1
    assert got[0]["category"] == "real" and got[0]["confidence"] == 0.9
    assert got[0]["evidence_bundle"] == {"k": "v"}


def test_save_triage_verdicts_rejects_non_member(repo, org):
    with pytest.raises(PermissionError):
        repo.save_triage_verdicts(user_id=str(uuid.uuid4()), org_id=org["org_id"],
                                  run_id=str(uuid.uuid4()), verdicts=[])


def test_get_triage_for_run_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="g2",
                           items=[_item("t1", "x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    assert repo.get_triage_for_run(user_id=str(uuid.uuid4()), run_id=r["run_id"]) == []


def test_set_family_label(repo, org):
    u, o = org["user_id"], org["org_id"]
    r = repo.ingest_ci_run(user_id=u, org_id=o, project="p", source="playwright", run_uid="lbl",
                           items=[_item("t1", "TimeoutError x", 1.0)],
                           results=[{"test_name": "t1", "status": "fail"}], snapshots=[])
    fam = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])["failures"][0]["family_id"]
    assert repo.set_family_label(user_id=u, family_id=fam, label="flaky") is True
    out = repo.get_triage_inputs(user_id=u, run_id=r["run_id"])
    assert out["failures"][0]["family_label"] == "flaky"


def test_set_family_label_rejects_invalid(repo, org):
    with pytest.raises(ValueError):
        repo.set_family_label(user_id=org["user_id"], family_id=str(uuid.uuid4()), label="bogus")
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_triage_repository.py -v -k "verdicts or label or triage_for_run"`
Expected: FAIL — `AttributeError: ... 'save_triage_verdicts'`.

- [ ] **Step 3: Implementar** — añadir los tres métodos (al final de `AssuranceRepository`)

```python
    def save_triage_verdicts(
        self, *, user_id: str, org_id: str, run_id: str, verdicts: List[Dict[str, Any]]
    ) -> int:
        """Reemplaza (delete+insert) los veredictos del run → idempotente. Lanza
        PermissionError si el usuario no es miembro del org."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select exists(select 1 from public.memberships"
                    " where org_id = %s and user_id = %s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute("delete from public.triage_verdicts where run_id = %s", (run_id,))
                for v in verdicts:
                    cur.execute(
                        "insert into public.triage_verdicts"
                        " (failure_id, run_id, org_id, category, confidence, rule_applied,"
                        "  evidence_bundle, requires_approval, llm_assisted, status)"
                        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (v["failure_id"], run_id, org_id, v["category"], v["confidence"],
                         v["rule_applied"], Json(v.get("evidence_bundle")),
                         v["requires_approval"], v["llm_assisted"], v.get("status", "resolved")),
                    )
            conn.commit()
        return len(verdicts)

    def get_triage_for_run(self, *, user_id: str, run_id: str) -> List[Dict[str, Any]]:
        """Veredictos persistidos de un run (vacío si no es miembro / no existe)."""
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "select tv.id, tv.failure_id, tv.category, tv.confidence, tv.rule_applied,"
                    "       tv.evidence_bundle, tv.requires_approval, tv.llm_assisted, tv.status"
                    " from public.triage_verdicts tv"
                    " join public.test_runs r on r.id = tv.run_id"
                    " where tv.run_id = %s and exists (select 1 from public.memberships m"
                    "   where m.org_id = r.org_id and m.user_id = %s)"
                    " order by tv.created_at",
                    (run_id, user_id),
                )
                return [
                    {
                        "id": str(r["id"]), "failure_id": str(r["failure_id"]),
                        "category": r["category"], "confidence": r["confidence"],
                        "rule_applied": r["rule_applied"], "evidence_bundle": r["evidence_bundle"],
                        "requires_approval": r["requires_approval"],
                        "llm_assisted": r["llm_assisted"], "status": r["status"],
                    }
                    for r in cur.fetchall()
                ]

    def set_family_label(self, *, user_id: str, family_id: str, label: str) -> bool:
        """Etiqueta una familia (lazo de aprendizaje / triaje). Devuelve False si no
        es miembro / no existe. Lanza ValueError si el label no es válido."""
        if label not in ("flaky", "real", "maintenance", "infra", "unknown"):
            raise ValueError(f"invalid label: {label!r}")
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    "update public.defect_families set label = %s"
                    " where id = %s and (scope = 'global' or exists (select 1 from public.memberships m"
                    "   where m.org_id = public.defect_families.org_id and m.user_id = %s))",
                    (label, family_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated
```

- [ ] **Step 4: Ejecutar (pasa) + suite completa**

Run: `pytest tests/test_triage_repository.py -v && pytest -m "not integration" -q`
Expected: integration de triaje PASS; suite unitaria completa verde (sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_triage_repository.py
git commit -m "feat(triage): persistencia de veredictos + set_family_label"
```

---

## Self-Review

**1. Cobertura del spec (F2d):**
- Migración 009 (`triage_verdicts` + `defect_families.label`, §8) → Task 1. ✓
- Señales de BD que alimentan `FailureInput` (§3.1: is_novel, family_label, retry_passed, intermittent_same_sha, has_green_baseline, dom_changed) → Task 3 (`get_triage_inputs`) + Task 2 (`dom_changed`). ✓
- `mass_cofailure` queda explícitamente fuera (lo calcula F2e, depende de `classify_error`). ✓
- Persistencia `save/get_triage_verdicts` (idempotente) + `set_family_label` (§6) → Task 4. ✓
- Lineage por familia (para el evidence_bundle de F2e) → Task 3. ✓

**2. Placeholders:** ninguno; todo paso lleva código/SQL completo y comando con salida esperada.

**3. Consistencia de tipos:** `get_triage_inputs` (Task 3) devuelve dicts con las claves que F2e mapeará a `FailureInput` (Task de F2bc); `save_triage_verdicts` (Task 4) consume dicts con `failure_id`/`category`/... que el servicio de F2e construirá desde `TriageVerdict` + `build_evidence`; `dom_changed` (Task 2) lo usa `get_triage_inputs` (Task 3). Categorías/labels/status coherentes con la migración 009.

**Nota de tamaño:** `src/defects/repository.py` crece con estos métodos. Sigue por debajo del límite (<800), pero si en F2e/F3 sigue creciendo, valorar extraer un `TriageRepository` aparte. No se hace ahora (mantener el patrón de una sola `AssuranceRepository`).

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-23-mnemo-autopilot-f2d-triage-repository.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> Continúa en `feat/mnemo-triage` (mismo PR de F2). Las Tasks 1, 3 y 4 tocan la BD (migración + tests `integration`); la Task 2 es pura. Tras F2d: **F2e** (TriageService que orquesta `get_triage_inputs` → mass_cofailure → `compute_signals` → `triage` → `build_evidence` → `save_triage_verdicts`, inline tras la ingesta) y **F2f** (desempate LLM).
