# Mnemo — Veredicto de aseguramiento (Plan 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generar el veredicto de aseguramiento de un run (conteos known/novel, señal de riesgo, familias recurrentes top + narrativa LLM) y exponerlo en `GET /v2/assurance/run/{id}`.

**Architecture:** `build_verdict` puro (determinista, testeable sin BD/LLM). Un `Narrator` (Protocol) inyectable con `LocalNarrator` (Ollama perezoso) para la narrativa. El repositorio añade `get_run_assurance_data`. El endpoint compone repo + verdict + narrator.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest. LLM Ollama local (mockeable). Branch `feat/mnemo-assurance`. `python3` desde la raíz; no usar `-m integration` salvo en la Task 3.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/multitenant_models.py` (extender) | `FamilyVerdict`, `AssuranceVerdictResponse` |
| `src/assurance/__init__.py` | paquete (vacío) |
| `src/assurance/verdict.py` | `build_verdict(*, run_summary, run_families)` — puro |
| `src/assurance/narrator.py` | `Narrator` (Protocol) + `LocalNarrator` (Ollama perezoso) |
| `src/defects/repository.py` (extender) | `get_run_assurance_data(*, user_id, run_id)` |
| `src/api_v2.py` (extender) | `get_narrator` dep + `GET /v2/assurance/run/{id}` |
| tests | `test_verdict.py`, `test_narrator.py`, `test_assurance_repository.py` (+1), `test_api_v2_assurance.py` |

---

## Task 1: build_verdict puro + modelos

**Files:**
- Create: `src/assurance/__init__.py`, `src/assurance/verdict.py`
- Modify: `src/multitenant_models.py`
- Test: `tests/test_verdict.py`

- [ ] **Step 1: Create the empty package file**

Create `src/assurance/__init__.py` (empty).

- [ ] **Step 2: Write the failing test**

Create `tests/test_verdict.py`:
```python
from src.assurance.verdict import build_verdict


def _fam(fid, title, occ, run_count):
    return {"id": fid, "title": title, "occurrence_count": occ, "run_count": run_count}


def test_verdict_counts_and_risk_attention_when_novel():
    v = build_verdict(run_summary={"ingested": 3, "known": 1, "novel": 2},
                      run_families=[_fam("f1", "Timeout", 5, 1)])
    assert v["ingested"] == 3 and v["known"] == 1 and v["novel"] == 2
    assert v["risk"] == "atencion"


def test_verdict_risk_ok_when_no_novel():
    v = build_verdict(run_summary={"ingested": 2, "known": 2, "novel": 0}, run_families=[])
    assert v["risk"] == "ok"


def test_verdict_top_families_sorted_and_recurring_flag():
    fams = [_fam("a", "A", 2, 2), _fam("b", "B", 9, 1), _fam("c", "C", 1, 1)]
    v = build_verdict(run_summary={"ingested": 3, "known": 1, "novel": 2}, run_families=fams)
    assert [f["id"] for f in v["top_families"]] == ["b", "a", "c"]  # por occurrence_count desc
    by_id = {f["id"]: f for f in v["top_families"]}
    assert by_id["b"]["recurring"] is True   # occ 9 > run_count 1
    assert by_id["a"]["recurring"] is False  # occ 2 == run_count 2


def test_verdict_top_families_capped_at_5():
    fams = [_fam(str(i), str(i), 10 - i, 1) for i in range(8)]
    v = build_verdict(run_summary={"ingested": 8, "known": 0, "novel": 8}, run_families=fams)
    assert len(v["top_families"]) == 5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Implement `src/assurance/verdict.py`**

```python
from typing import Any, Dict, List


def build_verdict(*, run_summary: Dict[str, Any], run_families: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Veredicto determinista de un run. La narrativa LLM se añade aparte (Narrator)."""
    known = int(run_summary.get("known", 0))
    novel = int(run_summary.get("novel", 0))
    ingested = int(run_summary.get("ingested", 0))
    ordered = sorted(run_families, key=lambda f: f["occurrence_count"], reverse=True)
    top = [
        {
            "id": str(f["id"]),
            "title": f["title"],
            "occurrence_count": f["occurrence_count"],
            "recurring": f["occurrence_count"] > f["run_count"],
        }
        for f in ordered[:5]
    ]
    return {
        "ingested": ingested,
        "known": known,
        "novel": novel,
        "risk": "atencion" if novel > 0 else "ok",
        "top_families": top,
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_verdict.py -v`
Expected: PASS (4).

- [ ] **Step 6: Append models to `src/multitenant_models.py`**

```python
class FamilyVerdict(BaseModel):
    id: str
    title: str
    occurrence_count: int
    recurring: bool


class AssuranceVerdictResponse(BaseModel):
    run_id: str
    ingested: int
    known: int
    novel: int
    risk: str
    top_families: List[FamilyVerdict] = Field(default_factory=list)
    narrative: Optional[str] = None
```

- [ ] **Step 7: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/assurance/__init__.py src/assurance/verdict.py src/multitenant_models.py tests/test_verdict.py
git commit -m "feat: add pure assurance verdict builder and response models"
```

---

## Task 2: Narrator (interfaz + local perezoso)

**Files:**
- Create: `src/assurance/narrator.py`
- Test: `tests/test_narrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_narrator.py`:
```python
from src.assurance.narrator import Narrator, LocalNarrator


def test_local_narrator_lazy():
    n = LocalNarrator()
    assert hasattr(n, "summarize")
    assert n._llm is None  # no carga el LLM hasta summarize


def test_fake_narrator_satisfies_protocol():
    class Fake:
        def summarize(self, verdict: dict) -> str:
            return "ok"

    def use(n: Narrator) -> str:
        return n.summarize({})

    assert use(Fake()) == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_narrator.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `src/assurance/narrator.py`**

```python
from typing import Any, Dict, Protocol, runtime_checkable

from src.config import MODEL_NAME, OLLAMA_BASE_URL


@runtime_checkable
class Narrator(Protocol):
    def summarize(self, verdict: Dict[str, Any]) -> str: ...


class LocalNarrator:
    """Narrativa via Ollama local. Carga el LLM de forma perezosa."""

    def __init__(self, model_name: str = MODEL_NAME):
        self._model_name = model_name
        self._llm = None

    def summarize(self, verdict: Dict[str, Any]) -> str:
        if self._llm is None:
            from langchain_ollama import OllamaLLM
            self._llm = OllamaLLM(model=self._model_name, base_url=OLLAMA_BASE_URL)
        recurring = [f["title"] for f in verdict.get("top_families", []) if f.get("recurring")]
        prompt = (
            "Eres un asistente de aseguramiento de calidad. Resume en 2-3 frases el resultado de un run de tests. "
            f"Datos: {verdict.get('known', 0)} fallos conocidos, {verdict.get('novel', 0)} nuevos, "
            f"riesgo='{verdict.get('risk', 'ok')}'. Familias recurrentes: {recurring or 'ninguna'}."
        )
        return self._llm.invoke(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_narrator.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/assurance/narrator.py tests/test_narrator.py
git commit -m "feat: add Narrator protocol and lazy LocalNarrator"
```

---

## Task 3: repository.get_run_assurance_data

**Files:**
- Modify: `src/defects/repository.py`
- Test: `tests/test_assurance_repository.py` (append)

- [ ] **Step 1: Append the failing integration test**

Append to `tests/test_assurance_repository.py`:
```python
def test_get_run_assurance_data(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure",
                          items=[_item("proj-a", "TimeoutException at host 10.0.0.1", "at A.java:1", 1.0),
                                 _item("proj-a", "NullPointer somewhere", "at B.java:2", 0.2)])
    run_id = out["run_id"]
    data = repo.get_run_assurance_data(user_id=u, run_id=run_id)
    assert data["run"] is not None
    assert data["summary"]["ingested"] == 2
    assert len(data["families"]) == 2
    for fam in data["families"]:
        assert fam["run_count"] >= 1 and "occurrence_count" in fam and "title" in fam


def test_get_run_assurance_data_non_member(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_run(user_id=u, org_id=o, project="p", source="allure",
                          items=[_item("p", "X error", None, 0.3)])
    other = str(uuid.uuid4())
    data = repo.get_run_assurance_data(user_id=other, run_id=out["run_id"])
    assert data["run"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_assurance_repository.py -v -m integration -k assurance_data`
Expected: FAIL — `AttributeError: 'AssuranceRepository' object has no attribute 'get_run_assurance_data'`.

- [ ] **Step 3: Add the method to `src/defects/repository.py`** (dentro de la clase, p.ej. tras `get_lineage`)

```python
    def get_run_assurance_data(self, *, user_id: str, run_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select r.id, r.project, r.source, r.summary
                    from public.test_runs r
                    where r.id = %s
                      and exists (select 1 from public.memberships m where m.org_id = r.org_id and m.user_id = %s)
                    """,
                    (run_id, user_id),
                )
                run = cur.fetchone()
                if run is None:
                    return {"run": None, "summary": {}, "families": []}
                cur.execute(
                    """
                    select df.id, df.title, df.occurrence_count, count(fl.id) as run_count
                    from public.failures fl
                    join public.defect_families df on df.id = fl.defect_family_id
                    where fl.run_id = %s
                    group by df.id
                    order by df.occurrence_count desc
                    """,
                    (run_id,),
                )
                families = [
                    {"id": str(r["id"]), "title": r["title"],
                     "occurrence_count": r["occurrence_count"], "run_count": r["run_count"]}
                    for r in cur.fetchall()
                ]
            return {
                "run": {"id": str(run["id"]), "project": run["project"], "source": run["source"]},
                "summary": run["summary"] or {},
                "families": families,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_assurance_repository.py -v -m integration -k assurance_data`
Expected: PASS (2). (Requiere `DATABASE_URL`.)

- [ ] **Step 5: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/defects/repository.py tests/test_assurance_repository.py
git commit -m "feat: add get_run_assurance_data to repository"
```

---

## Task 4: Endpoint `GET /v2/assurance/run/{id}`

**Files:**
- Modify: `src/api_v2.py`
- Test: `tests/test_api_v2_assurance.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_v2_assurance.py`:
```python
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(*, repo=None, narrator=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if narrator is not None:
        app.dependency_overrides[api_v2.get_narrator] = lambda: narrator
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_assurance_verdict_happy():
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {
        "run": {"id": "r1", "project": "proj-a", "source": "allure"},
        "summary": {"ingested": 3, "known": 1, "novel": 2},
        "families": [{"id": "f1", "title": "Timeout", "occurrence_count": 5, "run_count": 1}],
    }
    narrator = MagicMock()
    narrator.summarize.return_value = "Resumen del run."
    client = make_client(repo=repo, narrator=narrator)
    resp = client.get("/v2/assurance/run/r1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r1" and body["known"] == 1 and body["novel"] == 2
    assert body["risk"] == "atencion"
    assert body["top_families"][0]["id"] == "f1" and body["top_families"][0]["recurring"] is True
    assert body["narrative"] == "Resumen del run."


def test_assurance_verdict_not_found_is_404():
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {"run": None, "summary": {}, "families": []}
    client = make_client(repo=repo, narrator=MagicMock())
    resp = client.get("/v2/assurance/run/missing")
    assert resp.status_code == 404


def test_assurance_verdict_requires_auth():
    client = make_client(repo=MagicMock(), narrator=MagicMock(), with_user=False)
    resp = client.get("/v2/assurance/run/r1")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_v2_assurance.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_narrator'` o 404 de ruta.

- [ ] **Step 3: Edit `src/api_v2.py`**

(a) Ampliar el import de `src.multitenant_models` con `AssuranceVerdictResponse, FamilyVerdict` (mantener los existentes).
(b) Añadir imports:
```python
from src.assurance.verdict import build_verdict
from src.assurance.narrator import Narrator, LocalNarrator
```
(c) Añadir la dependencia perezosa del narrator (junto a las otras):
```python
_narrator = None


def get_narrator() -> Narrator:
    global _narrator
    if _narrator is None:
        _narrator = LocalNarrator()
    return _narrator
```
(d) Añadir el endpoint al final:
```python
@router.get("/assurance/run/{run_id}", response_model=AssuranceVerdictResponse)
def assurance_verdict_v2(
    run_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    repo: AssuranceRepository = Depends(get_assurance_repo),
    narrator: Narrator = Depends(get_narrator),
) -> AssuranceVerdictResponse:
    try:
        data = repo.get_run_assurance_data(user_id=user.user_id, run_id=run_id)
    except psycopg.Error as exc:
        raise HTTPException(status_code=502, detail="Database error") from exc
    if data["run"] is None:
        raise HTTPException(status_code=404, detail="run not found")
    verdict = build_verdict(run_summary=data["summary"], run_families=data["families"])
    narrative = narrator.summarize(verdict)
    return AssuranceVerdictResponse(
        run_id=run_id,
        ingested=verdict["ingested"], known=verdict["known"], novel=verdict["novel"],
        risk=verdict["risk"],
        top_families=[FamilyVerdict(**f) for f in verdict["top_families"]],
        narrative=narrative,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_v2_assurance.py -v`
Expected: PASS (3).

- [ ] **Step 5: Verify route mounts**

Run: `python3 -c "import api; assert '/v2/assurance/run/{run_id}' in [r.path for r in api.app.routes]; print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add src/api_v2.py tests/test_api_v2_assurance.py
git commit -m "feat: add GET /v2/assurance/run/{id} verdict endpoint"
```

---

## Task 5: Verificación

- [ ] **Step 1:** `python3 -m pytest -m "not integration" -q` → todo verde.
- [ ] **Step 2:** Code review del diff (mapeo de respuesta, 404, deps perezosas, pureza de build_verdict).

---

## Próximos planes

- **Plan 5:** frontend (páginas Assurance + Defect DNA, consumiendo `/v2/ingest/report`, `/v2/defects`, `/v2/assurance/run/{id}`).
- **Plan 6:** documentación (`docs/functional`, `docs/technical`, ADR) + poda legacy + `scripts/seed_demo.py`.
