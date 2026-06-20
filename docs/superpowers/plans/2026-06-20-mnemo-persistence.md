# Mnemo — Persistencia (Plan 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear el esquema de aseguramiento (`test_runs`/`failures`/`defect_families`) con RLS, un helper puro de actualización de centroide, y el repositorio `AssuranceRepository` que ingiere un run completo (match + persistencia + actualización de familia) y consulta familias y linaje.

**Architecture:** Migración SQL sobre el Postgres+pgvector existente (reusa `organizations`/`memberships` y la función `is_org_member` de la migración 001). Helper puro `update_centroid` (media móvil). `AssuranceRepository` sigue el patrón de `src/tenant_kb.py` (psycopg + `register_vector` + `set_config` de claims por transacción), usando la lógica pura del Plan 1 (`decide_match`, `fingerprint`).

**Tech Stack:** Python 3.13, Postgres + pgvector (Supabase, vía Session pooler), psycopg, pytest. Embeddings se inyectan (mockeables); el repo no los calcula.

**Branch:** `feat/mnemo-assurance` (ya creada, contiene el Plan 1). Ejecutar con `python3` desde la raíz `/Users/gonzalo/Documents/GitHub/SmartErrorDebugger`. La BD usa `DATABASE_URL` del `.env` (Session pooler `aws-1-eu-central-1.pooler.supabase.com:5432`).

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `db/migrations/002_assurance.sql` | Tablas `test_runs`/`failures`/`defect_families` + índices + RLS (+FORCE) + policies |
| `src/defects/centroid.py` | `update_centroid(centroid, count, vec)` — media móvil pura |
| `src/defects/repository.py` | `AssuranceRepository`: `ingest_run`, `list_defects`, `get_lineage` |
| `tests/test_centroid.py` | tests puros de la media móvil |
| `tests/test_assurance_repository.py` | tests de integración contra la BD real (marcados `integration`) |

---

## Task 1: Migración 002 (esquema + RLS) y aplicarla

**Files:**
- Create: `db/migrations/002_assurance.sql`

- [ ] **Step 1: Create `db/migrations/002_assurance.sql`**

```sql
-- Mnemo: esquema de aseguramiento (runs, failures, defect families)
create extension if not exists vector;

create table if not exists public.test_runs (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    project text not null,
    source text not null check (source in ('allure', 'junit')),
    ci_ref text,
    summary jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.defect_families (
    id uuid primary key default gen_random_uuid(),
    scope text not null check (scope in ('org', 'global')),
    org_id uuid references public.organizations (id) on delete cascade,
    signature text not null,
    title text not null,
    root_cause text,
    status text not null default 'open' check (status in ('open', 'resolved')),
    occurrence_count int not null default 0,
    centroid vector(384),
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint defect_families_scope_chk check (
        (scope = 'org' and org_id is not null) or (scope = 'global' and org_id is null)
    )
);

create table if not exists public.failures (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.test_runs (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    test_name text not null,
    error_type text,
    message text not null,
    trace text,
    fingerprint text not null,
    embedding vector(384),
    sanitized boolean not null default false,
    defect_family_id uuid references public.defect_families (id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists idx_runs_org on public.test_runs (org_id);
create index if not exists idx_failures_org on public.failures (org_id);
create index if not exists idx_failures_family on public.failures (defect_family_id);
create index if not exists idx_failures_fingerprint on public.failures (fingerprint);
create index if not exists idx_failures_embedding on public.failures using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index if not exists idx_families_org on public.defect_families (org_id) where org_id is not null;
create index if not exists idx_families_signature on public.defect_families (signature);

alter table public.test_runs enable row level security;
alter table public.failures enable row level security;
alter table public.defect_families enable row level security;
alter table public.test_runs force row level security;
alter table public.failures force row level security;
alter table public.defect_families force row level security;

drop policy if exists test_runs_member on public.test_runs;
create policy test_runs_member on public.test_runs for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

drop policy if exists failures_member on public.failures;
create policy failures_member on public.failures for all
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));

drop policy if exists defect_families_rw on public.defect_families;
create policy defect_families_rw on public.defect_families for all
    using (scope = 'global' or public.is_org_member(org_id))
    with check (scope = 'org' and public.is_org_member(org_id));

grant select, insert, update, delete on public.test_runs to authenticated;
grant select, insert, update, delete on public.failures to authenticated;
grant select, insert, update, delete on public.defect_families to authenticated;
```

- [ ] **Step 2: Apply the migration to Supabase**

Run (lee `DATABASE_URL` del `.env`, no lo imprime):
```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
DBURL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)
PGCONNECT_TIMEOUT=20 psql "$DBURL" -v ON_ERROR_STOP=1 -f db/migrations/002_assurance.sql
```
Expected: sin errores. **CONFIRMADO (2026-06-20):** el rol del pooler `postgres` tiene `rolbypassrls=true`, así que **RLS NO se aplica** vía la conexión directa. El aislamiento se hace en la **capa de aplicación** (filtros por membership en cada query del repositorio — ver Task 3). `FORCE RLS` queda como red de seguridad para el futuro (si se conecta vía un rol `authenticated` real / PostgREST). La migración ya está aplicada en Supabase.

- [ ] **Step 3: Verify tables exist**

```bash
DBURL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2-)
psql "$DBURL" -tA -c "select tablename from pg_tables where schemaname='public' and tablename in ('test_runs','failures','defect_families') order by tablename;"
```
Expected: `defect_families`, `failures`, `test_runs`.

- [ ] **Step 4: Commit**

```bash
git add db/migrations/002_assurance.sql
git commit -m "feat: add Mnemo assurance schema (runs/failures/defect_families) with RLS"
```

---

## Task 2: Helper puro de centroide (media móvil)

**Files:**
- Create: `src/defects/centroid.py`
- Test: `tests/test_centroid.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_centroid.py`:
```python
from src.defects.centroid import update_centroid


def test_update_centroid_from_empty():
    assert update_centroid(None, 0, [1.0, 3.0]) == [1.0, 3.0]


def test_update_centroid_running_mean():
    # centroide [2,2] con count=2, nuevo [8,8] -> (2*2+8)/3 = 4 en cada dim
    assert update_centroid([2.0, 2.0], 2, [8.0, 8.0]) == [4.0, 4.0]


def test_update_centroid_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        update_centroid([1.0, 2.0], 1, [1.0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_centroid.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.defects.centroid'`.

- [ ] **Step 3: Implement `src/defects/centroid.py`**

```python
from typing import List, Optional, Sequence


def update_centroid(centroid: Optional[Sequence[float]], count: int, vec: Sequence[float]) -> List[float]:
    """Media movil incremental: nuevo centroide tras observar `vec` (count = nº previo de miembros)."""
    if centroid is None or count <= 0:
        return list(vec)
    if len(centroid) != len(vec):
        raise ValueError(f"vector length mismatch: {len(centroid)} vs {len(vec)}")
    n = count + 1
    return [(c * count + v) / n for c, v in zip(centroid, vec)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_centroid.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/defects/centroid.py tests/test_centroid.py
git commit -m "feat: add running-mean centroid update helper"
```

---

## Task 3: AssuranceRepository (ingesta + consultas)

**Files:**
- Create: `src/defects/repository.py`
- Test: `tests/test_assurance_repository.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_assurance_repository.py`. Estos tests requieren BD real (marcados `integration`) y crean/limpian una org temporal.
```python
import os
import uuid

import pytest

pytestmark = pytest.mark.integration

from dotenv import load_dotenv

load_dotenv()

from src.ingest.models import FailureRecord
from src.defects.fingerprint import fingerprint
from src.defects.repository import AssuranceRepository, IngestItem

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
    # crea una org de prueba y un usuario "owner" via el claim; limpia al final
    user_id = str(uuid.uuid4())
    import psycopg
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")
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
        conn.commit()


def _item(project, msg, trace, seed):
    rec = FailureRecord(test_name="t", error_type="TimeoutException", message=msg, trace=trace, project=project, source="allure")
    return IngestItem(rec=rec, fingerprint=fingerprint(rec), embedding=_emb(seed))


def test_ingest_groups_same_error_across_projects(repo, org):
    u, o = org["user_id"], org["org_id"]
    # mismo error (volatiles distintos) en dos proyectos -> misma familia
    r1 = repo.ingest_run(user_id=u, org_id=o, project="proj-a", source="allure",
                         items=[_item("proj-a", "TimeoutException after 100ms", "at A.java:1", 1.0)])
    r2 = repo.ingest_run(user_id=u, org_id=o, project="proj-b", source="allure",
                         items=[_item("proj-b", "TimeoutException after 999ms", "at A.java:2", 1.0)])
    assert r1["known"] == 0 and r1["novel"] == 1
    assert r2["known"] == 1 and r2["novel"] == 0
    defects = repo.list_defects(user_id=u, org_id=o)
    assert len(defects) == 1
    assert defects[0]["occurrence_count"] == 2
    lineage = repo.get_lineage(user_id=u, defect_id=defects[0]["id"])
    projects = {f["project"] for f in lineage["failures"]}
    assert projects == {"proj-a", "proj-b"}


def test_isolation_between_orgs(repo, org):
    u, o = org["user_id"], org["org_id"]
    repo.ingest_run(user_id=u, org_id=o, project="p", source="allure",
                    items=[_item("p", "UniqueError xyz", None, 0.5)])
    other_user = str(uuid.uuid4())
    # otro usuario no miembro no ve los defects de esta org
    assert repo.list_defects(user_id=other_user, org_id=o) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_assurance_repository.py -v -m integration`
Expected: FAIL — `ImportError`/`ModuleNotFoundError` (repository/IngestItem no existen aún).

- [ ] **Step 3: Implement `src/defects/repository.py`**

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.config import DATABASE_URL
from src.defects.centroid import update_centroid
from src.defects.match import FamilyCandidate, decide_match
from src.ingest.models import FailureRecord


@dataclass
class IngestItem:
    rec: FailureRecord
    fingerprint: str
    embedding: Sequence[float]


class AssuranceRepository:
    def __init__(self, db_url: str = DATABASE_URL):
        if not db_url:
            raise RuntimeError("DATABASE_URL must be configured for Mnemo persistence")
        self.db_url = db_url

    def _connect(self):
        conn = psycopg.connect(self.db_url, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _set_claims(self, conn, user_id: str):
        with conn.cursor() as cur:
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")

    def _candidates(self, cur, *, org_id: str, embedding: Sequence[float], limit: int = 10) -> List[FamilyCandidate]:
        cur.execute(
            """
            select id, signature, centroid
            from public.defect_families
            where scope = 'org' and org_id = %s and centroid is not null
            order by centroid <=> %s
            limit %s
            """,
            (org_id, Vector(list(embedding)), limit),
        )
        rows = cur.fetchall()
        return [FamilyCandidate(family_id=str(r["id"]), signature=r["signature"], centroid=list(r["centroid"])) for r in rows]

    def ingest_run(self, *, user_id: str, org_id: str, project: str, source: str,
                   items: List[IngestItem]) -> Dict[str, Any]:
        known = 0
        novel = 0
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                # Aislamiento en capa de app: el rol del pooler hace BYPASS de RLS,
                # asi que verificamos membership explicitamente.
                cur.execute(
                    "select exists(select 1 from public.memberships where org_id=%s and user_id=%s) as ok",
                    (org_id, user_id),
                )
                if not cur.fetchone()["ok"]:
                    raise PermissionError("user is not a member of the organization")
                cur.execute(
                    "insert into public.test_runs (org_id, project, source) values (%s, %s, %s) returning id",
                    (org_id, project, source),
                )
                run_id = cur.fetchone()["id"]

                for item in items:
                    cands = self._candidates(cur, org_id=org_id, embedding=item.embedding)
                    decision = decide_match(fingerprint=item.fingerprint, embedding=item.embedding, candidates=cands)
                    if decision.is_new:
                        novel += 1
                        title = (item.rec.error_type or item.rec.message[:80] or "unknown")
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
                    else:
                        known += 1
                        family_id = decision.family_id
                        cur.execute(
                            "select occurrence_count, centroid from public.defect_families where id = %s",
                            (family_id,),
                        )
                        fam = cur.fetchone()
                        new_centroid = update_centroid(
                            list(fam["centroid"]) if fam["centroid"] is not None else None,
                            fam["occurrence_count"],
                            list(item.embedding),
                        )
                        cur.execute(
                            """
                            update public.defect_families
                            set occurrence_count = occurrence_count + 1,
                                last_seen = now(),
                                centroid = %s
                            where id = %s
                            """,
                            (Vector(new_centroid), family_id),
                        )

                    cur.execute(
                        """
                        insert into public.failures
                            (run_id, org_id, test_name, error_type, message, trace, fingerprint, embedding, sanitized, defect_family_id)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, true, %s)
                        """,
                        (run_id, org_id, item.rec.test_name, item.rec.error_type, item.rec.message,
                         item.rec.trace, item.fingerprint, Vector(list(item.embedding)), family_id),
                    )

                summary = {"ingested": len(items), "known": known, "novel": novel}
                cur.execute("update public.test_runs set summary = %s where id = %s",
                            (psycopg.types.json.Json(summary), run_id))
            conn.commit()
        return {"run_id": str(run_id), "ingested": len(items), "known": known, "novel": novel}

    def list_defects(self, *, user_id: str, org_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select f.id, f.title, f.status, f.occurrence_count, f.first_seen, f.last_seen,
                           coalesce(array_agg(distinct r.project) filter (where r.project is not null), '{}') as projects
                    from public.defect_families f
                    left join public.failures fl on fl.defect_family_id = f.id
                    left join public.test_runs r on r.id = fl.run_id
                    where f.scope = 'org' and f.org_id = %s
                      and exists (select 1 from public.memberships m where m.org_id = f.org_id and m.user_id = %s)
                    group by f.id
                    order by f.occurrence_count desc, f.last_seen desc
                    """,
                    (org_id, user_id),
                )
                return [
                    {
                        "id": str(r["id"]), "title": r["title"], "status": r["status"],
                        "occurrence_count": r["occurrence_count"],
                        "first_seen": str(r["first_seen"]), "last_seen": str(r["last_seen"]),
                        "projects": list(r["projects"]),
                    }
                    for r in cur.fetchall()
                ]

    def get_lineage(self, *, user_id: str, defect_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            self._set_claims(conn, user_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select f.id, f.title, f.status, f.occurrence_count
                    from public.defect_families f
                    where f.id = %s
                      and (f.scope = 'global'
                           or exists (select 1 from public.memberships m where m.org_id = f.org_id and m.user_id = %s))
                    """,
                    (defect_id, user_id),
                )
                fam = cur.fetchone()
                if fam is None:
                    return {"family": None, "failures": []}
                cur.execute(
                    """
                    select fl.id, fl.test_name, fl.error_type, fl.created_at, r.project, r.source
                    from public.failures fl
                    join public.test_runs r on r.id = fl.run_id
                    where fl.defect_family_id = %s
                    order by fl.created_at
                    """,
                    (defect_id,),
                )
                failures = [
                    {"id": str(r["id"]), "test_name": r["test_name"], "error_type": r["error_type"],
                     "project": r["project"], "source": r["source"], "created_at": str(r["created_at"])}
                    for r in cur.fetchall()
                ]
            return {
                "family": {"id": str(fam["id"]), "title": fam["title"], "status": fam["status"],
                           "occurrence_count": fam["occurrence_count"]},
                "failures": failures,
            }
```

- [ ] **Step 4: Run integration tests to verify they pass**

Run: `python3 -m pytest tests/test_assurance_repository.py -v -m integration`
Expected: PASS (2 tests). Requiere `DATABASE_URL` (Session pooler) accesible. Si `test_isolation_between_orgs` falla porque el otro usuario SÍ ve los defects, es un fallo de RLS real — reportar (no debilitar el test). Si la inserción de la app falla por `FORCE RLS`, ver nota de la Task 1.

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_assurance_repository.py
git commit -m "feat: add AssuranceRepository (ingest_run, list_defects, get_lineage)"
```

---

## Task 4: Verificación

- [ ] **Step 1: Unit suite (sin integración) sigue verde**

Run: `python3 -m pytest -m "not integration" -q`
Expected: PASS (incluye `test_centroid` y todo lo previo; los tests de `test_assurance_repository` quedan deseleccionados).

- [ ] **Step 2: Code review**

`code-reviewer`/`python-reviewer` sobre el diff de las 3 tareas. Verificar SQL parametrizado (sin inyección), uso correcto de `Vector`, y el aislamiento RLS.

---

## Próximos planes

- **Plan 3:** servicio de ingesta (parse→sanitize→fingerprint→embed→`ingest_run`) + endpoints `POST /v2/ingest/report`, `GET /v2/defects`, `GET /v2/defects/{id}` (tests con repo/embedder mockeados).
- **Plan 4:** veredicto de aseguramiento (LLM async) + `GET /v2/assurance/run/{id}`.
- **Plan 5:** frontend (Assurance + Defect DNA).
- **Plan 6:** docs + poda legacy + seed de demo.
