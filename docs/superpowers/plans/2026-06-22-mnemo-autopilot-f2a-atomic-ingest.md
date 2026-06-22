# Mnemo Autopilot — F2a: ingesta atómica + idempotente Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sustituir la ingesta de CI en 3 transacciones por un único método **atómico** `ingest_ci_run` (run + failures + familias + test_results + dom_snapshots en una transacción), **idempotente** por `run_uid` para que un reintento del CI no duplique runs ni corrompa el Defect DNA.

**Architecture:** Se extrae el emparejamiento de un fallo a su familia a un helper privado reutilizable; `ingest_run` (legacy, caminos Allure/JUnit/Jira) lo usa sin cambiar de comportamiento, y el nuevo `ingest_ci_run` lo usa dentro de una transacción única con dedup por `(org_id, run_uid)`. `CiIngestionService` pasa a llamar al método atómico. La clave de idempotencia es un `run_uid` (UUID por run del CI), **no** el commit, para preservar la señal de intermitencia mismo-SHA.

**Tech Stack:** Python 3.13, FastAPI, psycopg (dict_row), pgvector, Postgres (Supabase), Pydantic v2, pytest.

## Global Constraints

- Aislamiento multitenant: el pooler hace **BYPASS de RLS** → el aislamiento real es el **chequeo de membership en la capa de aplicación**. NUNCA quitarlo (`src/defects/repository.py`).
- **Atomicidad:** `ingest_ci_run` hace run+failures+familias+test_results+dom_snapshots en **UNA** transacción (`with self._connect() as conn: … conn.commit()`); cualquier excepción revierte todo (el context manager de psycopg hace rollback).
- **Idempotencia:** dedup por `(org_id, run_uid)`. Si `run_uid` viene y ya existe → **no-op** devolviendo el run existente con `deduplicated=True`. Si `run_uid` falta → solo atomicidad (retrocompatible).
- `ingest_run` (legacy) se conserva intacto en comportamiento; la extracción del helper la verifican sus tests integration existentes (`tests/test_assurance_repository.py`).
- Tests sin BD vía mocks: `pytest -m "not integration"`. Los de repositorio llevan `pytestmark = pytest.mark.integration` y corren contra Postgres con la **migración 008 aplicada** (`DATABASE_URL` en `.env`, `load_dotenv`).
- Embeddings `vector(384)`. Migración siguiente libre: **008** (007 ya existe). Commit: `<type>: <description>`.

---

### Task 1: Migración 008 — `test_runs.run_uid` + índice único parcial

**Files:**
- Create: `db/migrations/008_run_uid.sql`

**Interfaces:**
- Produces: columna `public.test_runs.run_uid text`; índice único parcial `idx_test_runs_run_uid` sobre `(org_id, run_uid) where run_uid is not null`.

- [ ] **Step 1: Escribir la migración**

```sql
-- db/migrations/008_run_uid.sql
-- Mnemo Autopilot F2a: idempotencia de ingesta por identificador de run del CI.
-- run_uid es un UUID que el reporter genera UNA vez por run. Dedup por (org_id, run_uid):
-- un reintento de la misma entrega → no-op; una re-ejecución (mismo commit, otro run) → run nuevo.
-- El índice es PARCIAL: los runs sin run_uid (caminos legacy) no se ven afectados.

alter table public.test_runs add column if not exists run_uid text;

create unique index if not exists idx_test_runs_run_uid
    on public.test_runs (org_id, run_uid)
    where run_uid is not null;
```

- [ ] **Step 2: Aplicar la migración**

Run: `export DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"') && psql "$DATABASE_URL" -f db/migrations/008_run_uid.sql`
Expected: `ALTER TABLE` y `CREATE INDEX` sin errores.

- [ ] **Step 3: Verificar**

Run: `psql "$DATABASE_URL" -c "\d public.test_runs"`
Expected: `test_runs` incluye `run_uid text` y el índice `idx_test_runs_run_uid` (UNIQUE, parcial).

- [ ] **Step 4: Commit**

```bash
git add db/migrations/008_run_uid.sql
git commit -m "feat: migración 008 (test_runs.run_uid + índice único parcial para idempotencia)"
```

---

### Task 2: `CiRunArtifact.run_uid` (campo opcional del contrato)

**Files:**
- Modify: `src/ci/models.py` (clase `CiRunArtifact`)
- Test: `tests/test_ci_models.py` (añadir test)

**Interfaces:**
- Consumes: `CiRunArtifact` existente (`project`, `org_id`, `commit_sha`, `source`, `tests`).
- Produces: `CiRunArtifact.run_uid: Optional[str]` (default `None`, `max_length=200`).

- [ ] **Step 1: Escribir el test**

```python
# tests/test_ci_models.py — añadir
def test_run_uid_optional_default_none():
    art = CiRunArtifact.model_validate(
        {"project": "p", "org_id": "o", "commit_sha": "abc", "tests": []}
    )
    assert art.run_uid is None
    art2 = CiRunArtifact.model_validate(
        {"project": "p", "org_id": "o", "commit_sha": "abc", "run_uid": "u-123", "tests": []}
    )
    assert art2.run_uid == "u-123"
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_models.py::test_run_uid_optional_default_none -v`
Expected: FAIL — `art.run_uid` no existe (`AttributeError`).

- [ ] **Step 3: Implementar** — añadir el campo a `CiRunArtifact` en `src/ci/models.py`

```python
class CiRunArtifact(BaseModel):
    project: str = Field(max_length=500)
    org_id: str = Field(max_length=200)
    commit_sha: str = Field(max_length=200)
    source: str = "playwright"
    run_uid: Optional[str] = Field(default=None, max_length=200)
    tests: List[CiTestResult] = Field(max_length=10_000)
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_ci_models.py -v`
Expected: todos PASS (incluido el nuevo).

- [ ] **Step 5: Commit**

```bash
git add src/ci/models.py tests/test_ci_models.py
git commit -m "feat: CiRunArtifact.run_uid (identificador de run del CI, opcional)"
```

---

### Task 3: Extraer `_match_and_insert_failure` y refactorizar `ingest_run`

**Files:**
- Modify: `src/defects/repository.py` (clase `AssuranceRepository`: añadir helper, refactorizar el bucle de `ingest_run`)

**Interfaces:**
- Consumes: `_query_candidates`, `decide_match`, `update_centroid`, `IngestItem`, `Vector` (ya en el módulo).
- Produces: `AssuranceRepository._match_and_insert_failure(cur, *, org_id: str, run_id, item: IngestItem) -> bool` (True si la familia es nueva, False si conocida; inserta la fila de `failures`).

> Refactor **que preserva el comportamiento**: el bucle de `ingest_run` pasa a llamar al helper. Los tests integration existentes de `ingest_run` (`tests/test_assurance_repository.py`) deben seguir verdes — son la red que valida esta tarea.

- [ ] **Step 1: Añadir el helper** (en la clase `AssuranceRepository`, antes de `ingest_run`)

```python
    def _match_and_insert_failure(self, cur, *, org_id: str, run_id, item: IngestItem) -> bool:
        """Empareja un fallo con su familia (crea o actualiza centroide/contador) e inserta
        la fila de `failures`. Devuelve True si la familia es nueva (novel), False si conocida.
        Debe ejecutarse dentro de una transacción abierta (recibe el cursor)."""
        cands = self._query_candidates(
            cur, org_id=org_id, fingerprint=item.fingerprint, embedding=item.embedding
        )
        decision = decide_match(
            fingerprint=item.fingerprint, embedding=item.embedding, candidates=cands,
        )
        if decision.is_new:
            title = item.rec.error_type or item.rec.message[:80] or "unknown"
            cur.execute(
                """
                insert into public.defect_families
                    (scope, org_id, signature, title, occurrence_count, centroid)
                values ('org', %s, %s, %s, 1, %s)
                returning id
                """,
                (org_id, item.fingerprint, title, Vector(list(item.embedding))),
            )
            family_id = cur.fetchone()["id"]
            is_new = True
        else:
            family_id = decision.family_id
            cur.execute(
                "select occurrence_count, centroid"
                " from public.defect_families where id = %s for update",
                (family_id,),
            )
            fam = cur.fetchone()
            new_centroid = update_centroid(
                list(fam["centroid"]) if fam["centroid"] is not None else None,
                fam["occurrence_count"], list(item.embedding),
            )
            cur.execute(
                """
                update public.defect_families
                set occurrence_count = occurrence_count + 1, last_seen = now(), centroid = %s
                where id = %s
                """,
                (Vector(new_centroid), family_id),
            )
            is_new = False
        cur.execute(
            """
            insert into public.failures
                (run_id, org_id, test_name, error_type, message, trace,
                 fingerprint, embedding, sanitized, defect_family_id,
                 external_ref, external_url)
            values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s)
            """,
            (run_id, org_id, item.rec.test_name, item.rec.error_type, item.rec.message,
             item.rec.trace, item.fingerprint, Vector(list(item.embedding)), family_id,
             item.external_ref, item.external_url),
        )
        return is_new
```

- [ ] **Step 2: Refactorizar el bucle de `ingest_run`** para usar el helper. Reemplaza el bloque `for item in items:` (desde `cands = self._query_candidates(...)` hasta el `insert into public.failures ...` incluido) por:

```python
                for item in items:
                    if self._match_and_insert_failure(cur, org_id=org_id, run_id=run_id, item=item):
                        novel += 1
                    else:
                        known += 1
```

- [ ] **Step 3: Ejecutar los tests de `ingest_run` (deben seguir verdes — sin cambios de comportamiento)**

Run: `pytest tests/test_assurance_repository.py tests/test_ci_repository.py -v`
Expected: todos PASS (mismo comportamiento que antes del refactor).

- [ ] **Step 4: Commit**

```bash
git add src/defects/repository.py
git commit -m "refactor: extraer _match_and_insert_failure reutilizable de ingest_run"
```

---

### Task 4: `ingest_ci_run` atómico + idempotente

**Files:**
- Modify: `src/defects/repository.py` (añadir `ingest_ci_run`)
- Test: `tests/test_ci_repository.py` (integration)

**Interfaces:**
- Consumes: `_match_and_insert_failure` (Task 3), `_connect`/`_set_claims`, `Json`.
- Produces: `ingest_ci_run(*, user_id, org_id, project, source, commit_sha=None, run_uid=None, items, results, snapshots) -> dict` con claves `{run_id, ingested, known, novel, results_recorded, snapshots_saved, deduplicated}`. Atómico (una transacción) e idempotente por `(org_id, run_uid)`.

- [ ] **Step 1: Escribir los tests (integration)** — añadir a `tests/test_ci_repository.py` (usa los fixtures `repo`/`org` y `_failure_item` existentes)

```python
def test_ingest_ci_run_atomic_and_counts(repo, org):
    u, o = org["user_id"], org["org_id"]
    out = repo.ingest_ci_run(
        user_id=u, org_id=o, project="p", source="playwright",
        commit_sha="sha", run_uid="run-1",
        items=[_failure_item("p", "TimeoutError x", 1.0)],
        results=[{"test_name": "login", "status": "fail", "retried": False},
                 {"test_name": "home", "status": "pass", "retried": False}],
        snapshots=[{"test_name": "home", "kind": "last_green", "content": "<html>ok</html>",
                    "commit_sha": "sha"}],
    )
    assert out["deduplicated"] is False
    assert out["ingested"] == 1 and out["novel"] == 1
    assert out["results_recorded"] == 2 and out["snapshots_saved"] == 1
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_results where run_id = %s", (out["run_id"],))
            assert cur.fetchone()[0] == 2


def test_ingest_ci_run_idempotent_by_run_uid(repo, org):
    u, o = org["user_id"], org["org_id"]
    kw = dict(user_id=u, org_id=o, project="p", source="playwright", commit_sha="sha",
              run_uid="dup-1",
              items=[_failure_item("p", "TimeoutError x", 1.0)],
              results=[{"test_name": "t", "status": "fail"}],
              snapshots=[])
    first = repo.ingest_ci_run(**kw)
    second = repo.ingest_ci_run(**kw)
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert second["run_id"] == first["run_id"]
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_runs where org_id = %s and run_uid = %s",
                        (o, "dup-1"))
            assert cur.fetchone()[0] == 1


def test_ingest_ci_run_rolls_back_on_bad_snapshot(repo, org):
    u, o = org["user_id"], org["org_id"]
    with pytest.raises(ValueError):
        repo.ingest_ci_run(
            user_id=u, org_id=o, project="p", source="playwright", commit_sha="sha",
            run_uid="rollback-1",
            items=[_failure_item("p", "TimeoutError x", 1.0)],
            results=[{"test_name": "t", "status": "fail"}],
            snapshots=[{"test_name": "t", "kind": "bogus", "content": "<html></html>"}],
        )
    # Atomicidad: el run NO debe haberse creado.
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.test_runs where org_id = %s and run_uid = %s",
                        (o, "rollback-1"))
            assert cur.fetchone()[0] == 0


def test_ingest_ci_run_rejects_non_member(repo, org):
    with pytest.raises(PermissionError):
        repo.ingest_ci_run(user_id=str(uuid.uuid4()), org_id=org["org_id"], project="p",
                           source="playwright", run_uid="x", items=[], results=[], snapshots=[])
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_repository.py -v -k ingest_ci_run`
Expected: FAIL — `AttributeError: 'AssuranceRepository' object has no attribute 'ingest_ci_run'`.

- [ ] **Step 3: Implementar `ingest_ci_run`** (en `AssuranceRepository`, tras `ingest_run`)

```python
    def ingest_ci_run(
        self,
        *,
        user_id: str,
        org_id: str,
        project: str,
        source: str,
        commit_sha: Optional[str] = None,
        run_uid: Optional[str] = None,
        items: List[IngestItem],
        results: List[Dict[str, Any]],
        snapshots: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Ingesta atómica de un run de CI: run + failures + familias + test_results +
        dom_snapshots en UNA transacción. Idempotente por (org_id, run_uid): si run_uid
        viene y ya existe, no-op devolviendo el run existente con deduplicated=True.

        Lanza PermissionError si no es miembro; ValueError ante status/kind inválido.
        """
        _STATUS = ("pass", "fail", "flaky", "skipped")
        _KINDS = ("last_green", "failure")
        known = 0
        novel = 0
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

                if run_uid is not None:
                    cur.execute(
                        "select id, summary from public.test_runs"
                        " where org_id = %s and run_uid = %s",
                        (org_id, run_uid),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        summary = existing["summary"] or {}
                        return {
                            "run_id": str(existing["id"]),
                            "ingested": summary.get("ingested", 0),
                            "known": summary.get("known", 0),
                            "novel": summary.get("novel", 0),
                            "results_recorded": 0,
                            "snapshots_saved": 0,
                            "deduplicated": True,
                        }

                cur.execute(
                    "insert into public.test_runs (org_id, project, source, commit_sha, run_uid)"
                    " values (%s, %s, %s, %s, %s) returning id",
                    (org_id, project, source, commit_sha, run_uid),
                )
                run_id = cur.fetchone()["id"]

                for item in items:
                    if self._match_and_insert_failure(cur, org_id=org_id, run_id=run_id, item=item):
                        novel += 1
                    else:
                        known += 1

                for r in results:
                    if "test_name" not in r or "status" not in r:
                        raise ValueError("each result requires 'test_name' and 'status'")
                    if r["status"] not in _STATUS:
                        raise ValueError(f"invalid status: {r['status']!r}")
                    cur.execute(
                        "insert into public.test_results"
                        " (run_id, org_id, test_name, status, retried)"
                        " values (%s, %s, %s, %s, %s)",
                        (run_id, org_id, r["test_name"], r["status"], r.get("retried", False)),
                    )

                for s in snapshots:
                    if "test_name" not in s or "kind" not in s or "content" not in s:
                        raise ValueError("each snapshot requires 'test_name', 'kind' and 'content'")
                    if s["kind"] not in _KINDS:
                        raise ValueError(f"invalid kind: {s['kind']!r}")
                    cur.execute(
                        "insert into public.dom_snapshots"
                        " (org_id, project, test_name, kind, content, commit_sha)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (org_id, project, s["test_name"], s["kind"], s["content"],
                         s.get("commit_sha")),
                    )

                summary = {"ingested": len(items), "known": known, "novel": novel}
                cur.execute(
                    "update public.test_runs set summary = %s where id = %s",
                    (Json(summary), run_id),
                )
            conn.commit()
        return {
            "run_id": str(run_id),
            "ingested": len(items),
            "known": known,
            "novel": novel,
            "results_recorded": len(results),
            "snapshots_saved": len(snapshots),
            "deduplicated": False,
        }
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `pytest tests/test_ci_repository.py -v`
Expected: todos PASS (los 4 nuevos + los existentes).

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_ci_repository.py
git commit -m "feat: ingest_ci_run atómico e idempotente por run_uid"
```

---

### Task 5: `CiIngestionService` usa `ingest_ci_run`

**Files:**
- Modify: `src/ci/ingestion_service.py` (`ingest_artifact`)
- Test: `tests/test_ci_ingestion_service.py` (actualizar a la orquestación de un solo método)

**Interfaces:**
- Consumes: `AssuranceRepository.ingest_ci_run` (Task 4), `CiRunArtifact.run_uid` (Task 2), `to_failure_records`, `sanitize_text`, `fingerprint`, `Embedder`.
- Produces: `CiIngestionService.ingest_artifact(*, user_id, artifact) -> dict` que construye items+results+snapshots y delega en `ingest_ci_run` (una sola llamada).

- [ ] **Step 1: Actualizar los tests** (reescribir `tests/test_ci_ingestion_service.py` para la orquestación de un solo método)

```python
from unittest.mock import MagicMock

from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact


def _artifact(run_uid=None):
    return CiRunArtifact.model_validate({
        "project": "demo", "org_id": "org-1", "commit_sha": "abc", "run_uid": run_uid,
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html>fail</html>"},
            {"test_name": "home", "status": "pass", "dom": "<html>ok</html>"},
            {"test_name": "skip_me", "status": "skipped"},
        ],
    })


def _service():
    repo = MagicMock()
    repo.ingest_ci_run.return_value = {
        "run_id": "r1", "ingested": 1, "known": 0, "novel": 1,
        "results_recorded": 3, "snapshots_saved": 2, "deduplicated": False,
    }
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 384
    return CiIngestionService(repo=repo, embedder=embedder), repo


def test_calls_ingest_ci_run_once_with_items_results_snapshots():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact(run_uid="u-1"))
    repo.ingest_ci_run.assert_called_once()
    _, kw = repo.ingest_ci_run.call_args
    assert kw["org_id"] == "org-1" and kw["commit_sha"] == "abc" and kw["run_uid"] == "u-1"
    # items = solo fallos (login); results = todos los tests; snapshots = los que tienen dom
    assert len(kw["items"]) == 1 and kw["items"][0].rec.test_name == "login"
    assert {r["test_name"] for r in kw["results"]} == {"login", "home", "skip_me"}
    assert {s["test_name"]: s["kind"] for s in kw["snapshots"]} == {"login": "failure", "home": "last_green"}


def test_returns_repo_result_passthrough():
    svc, _ = _service()
    out = svc.ingest_artifact(user_id="svc", artifact=_artifact())
    assert out["run_id"] == "r1" and out["deduplicated"] is False
    assert out["results_recorded"] == 3 and out["snapshots_saved"] == 2
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `pytest tests/test_ci_ingestion_service.py -v`
Expected: FAIL — el mock no tiene `ingest_ci_run` configurado en el código aún / el servicio llama a los métodos viejos.

- [ ] **Step 3: Reescribir `ingest_artifact`** en `src/ci/ingestion_service.py`

```python
    def ingest_artifact(self, *, user_id: str, artifact: CiRunArtifact) -> Dict[str, Any]:
        """Ingesta atómica e idempotente de un artefacto de CI: fallos→Defect DNA +
        resultados por test + snapshots DOM, en una sola transacción. Idempotente por run_uid."""
        items = []
        for rec in to_failure_records(artifact):
            message = sanitize_text(rec.message)
            trace = sanitize_text(rec.trace) if rec.trace else None
            clean = replace(rec, message=message, trace=trace)
            fp = fingerprint(clean)
            embedding = self.embedder.embed(f"{clean.error_type or ''} {message}".strip())
            items.append(IngestItem(rec=clean, fingerprint=fp, embedding=embedding))

        results = [
            {"test_name": t.test_name, "status": t.status, "retried": t.retried}
            for t in artifact.tests
        ]
        snapshots = [
            {
                "test_name": t.test_name,
                "kind": "last_green" if t.status == "pass" else "failure",
                "content": t.dom,
                "commit_sha": artifact.commit_sha,
            }
            for t in artifact.tests
            if t.dom
        ]

        return self.repo.ingest_ci_run(
            user_id=user_id, org_id=artifact.org_id, project=artifact.project,
            source=artifact.source, commit_sha=artifact.commit_sha, run_uid=artifact.run_uid,
            items=items, results=results, snapshots=snapshots,
        )
```

- [ ] **Step 4: Ejecutar (pasa) + suite unitaria completa**

Run: `pytest tests/test_ci_ingestion_service.py -v && pytest -m "not integration" -q`
Expected: tests del servicio PASS; suite unitaria completa verde (sin regresiones).

- [ ] **Step 5: Commit**

```bash
git add src/ci/ingestion_service.py tests/test_ci_ingestion_service.py
git commit -m "refactor: CiIngestionService usa ingest_ci_run atómico/idempotente"
```

---

## Self-Review

**1. Cobertura del spec (F2a):**
- Ingesta atómica (una transacción) → Task 4 (`ingest_ci_run`). ✓
- Idempotencia por `run_uid` (no-op en reintento, run nuevo en re-ejecución) → Task 1 (índice) + Task 4 (dedup). ✓
- `run_uid` opcional en el contrato → Task 2. ✓
- `ingest_run` legacy intacto (vía helper compartido) → Task 3 (refactor verificado por tests existentes). ✓
- Servicio usa el método atómico → Task 5. ✓

**2. Placeholders:** ninguno; todo paso de código lleva el código completo y cada comando su salida esperada.

**3. Consistencia de tipos:** `_match_and_insert_failure(cur, *, org_id, run_id, item) -> bool` (Task 3) lo usa `ingest_ci_run` (Task 4) e `ingest_run` (Task 3); `ingest_ci_run(... run_uid ..., items, results, snapshots)` (Task 4) lo llama `CiIngestionService` (Task 5) con `artifact.run_uid` (Task 2); la clave de retorno `deduplicated` es consistente entre Task 4 y los tests de Task 5.

**Nota:** el reporter (F1b, otra rama) debe poblar `run_uid` para que la dedup se active; mientras tanto, `run_uid=None` → solo atomicidad (retrocompatible). Ese cambio del reporter es un follow-up pequeño fuera de F2a.

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-22-mnemo-autopilot-f2a-atomic-ingest.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea + revisión de dos etapas.
2. **Inline Execution** — ejecución por lotes con checkpoints.

> F2a es la primera de las 6 fases de F2 (ver §11 del spec de F2). Tras F2a vendrán F2b/F2c (motor puro), F2d (repo de triaje), F2e (servicio+wiring), F2f (tiebreaker+endpoint), cada una con su plan.
> Las Tasks 1 y 4 tocan la BD (migración + tests `integration`); el resto corre con mocks.
