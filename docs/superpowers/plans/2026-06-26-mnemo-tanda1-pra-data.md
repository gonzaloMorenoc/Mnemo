# Tanda 1 · PR-A — Migración 016 + correctitud de ingesta/triaje — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar B1/A6/A8/A9 (migración 016: force RLS + índices + hoist + ivfflat parciales), B3 (idempotencia de ingesta) y A3/A4 (métrica del foso honesta + sin familia duplicada) de la auditoría.

**Architecture:** Una migración SQL idempotente aplicada a la BD de producción + tres cambios quirúrgicos en `src/defects/repository.py`. Tests de integración contra Postgres.

**Tech Stack:** PostgreSQL/Supabase (pgvector), Python/psycopg, pytest (`@pytest.mark.integration`).

## Global Constraints

- `DATABASE_URL` (.env) **es producción**: aplicar `016` con `psql` (Bash con `dangerouslyDisableSandbox`). Verificar tras aplicar.
- **Invariante RLS:** toda tabla `public` con `enable`+`force`+policy. Esta migración añade el `force` que faltaba en las 7 tablas de 001.
- Tests de integración con cleanup en fixtures (reusar el patrón de `tests/test_triage_repository.py` / `test_certify_repository.py`: crear `auth.users`+org (trigger auto-enrola owner)+familia/run, teardown borra org+user).
- Commits `feat:`/`fix:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`. Tests con `python3 -m pytest`.

---

## Task 1: Migración `016_hardening.sql` (B1 + A6 + A8 + A9)

**Files:** Create `db/migrations/016_hardening.sql`; Test `tests/test_migration_016_rls.py`.

**Interfaces:** Produces — `force row level security` en `profiles, organizations, memberships, documents, chunks, embeddings, analyses`; índices `idx_triage_verdicts_failure, idx_actions_verdict, idx_triage_corrections_family, idx_test_runs_commit, idx_certificates_org`; `is_org_member` con `(select auth.uid())`; ivfflat parciales.

- [ ] **Step 1: Write the migration** — `db/migrations/016_hardening.sql`:

```sql
-- db/migrations/016_hardening.sql
-- Tanda 1 (auditoría 2026-06-25): force RLS en las tablas base de 001, índices FK
-- en hot paths, is_org_member hoisteable, e ivfflat parciales (excluir NULLs).

-- B1: las 7 tablas de 001 tenían enable pero NO force. RLS no aplicaba al owner.
alter table public.profiles      force row level security;
alter table public.organizations force row level security;
alter table public.memberships   force row level security;
alter table public.documents     force row level security;
alter table public.chunks        force row level security;
alter table public.embeddings    force row level security;
alter table public.analyses      force row level security;

-- A8: subconsulta para que el planner pueda hoistar auth.uid() (no per-row).
create or replace function public.is_org_member(target_org_id uuid)
returns boolean
language sql
stable
as $$
    select exists (
        select 1 from public.memberships m
        where m.org_id = target_org_id
          and m.user_id = (select auth.uid())
    );
$$;

-- A6: índices FK faltantes en hot paths.
create index if not exists idx_triage_verdicts_failure on public.triage_verdicts (failure_id);
create index if not exists idx_actions_verdict on public.actions (triage_verdict_id);
create index if not exists idx_triage_corrections_family on public.triage_corrections (family_id);
create index if not exists idx_test_runs_commit on public.test_runs (org_id, project, commit_sha)
    where commit_sha is not null;
create index if not exists idx_certificates_org on public.certificates (org_id);

-- A9: ivfflat parciales (el índice ya no almacena filas con NULL).
drop index if exists public.idx_failures_embedding;
create index idx_failures_embedding on public.failures
    using ivfflat (embedding vector_cosine_ops) with (lists = 100)
    where embedding is not null;
drop index if exists public.idx_families_centroid;
create index idx_families_centroid on public.defect_families
    using ivfflat (centroid vector_cosine_ops) with (lists = 100)
    where centroid is not null;
```

- [ ] **Step 2: Apply to the DB (production) and verify**

Run (Bash, `dangerouslyDisableSandbox`): `set -a && source .env && set +a && psql "$DATABASE_URL" -f db/migrations/016_hardening.sql`
Then verify (must show `t | t` for the 7 base tables): `psql "$DATABASE_URL" -c "select relname, relrowsecurity, relforcerowsecurity from pg_class where relnamespace='public'::regnamespace and relkind='r' and relname in ('profiles','organizations','memberships','documents','chunks','embeddings','analyses') order by relname;"`

- [ ] **Step 3: Write the failing integration test** — `tests/test_migration_016_rls.py`:

```python
import os

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

DBURL = os.getenv("DATABASE_URL", "")

_BASE_TABLES = ["profiles", "organizations", "memberships", "documents",
                "chunks", "embeddings", "analyses"]


def _rls_flags():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute(
            "select relname, relrowsecurity, relforcerowsecurity from pg_class"
            " where relnamespace = 'public'::regnamespace and relkind = 'r'"
            "   and relname = any(%s)", (_BASE_TABLES,))
        return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


def test_base_tables_have_rls_enabled_and_forced():
    flags = _rls_flags()
    for t in _BASE_TABLES:
        assert t in flags, f"tabla {t} no encontrada"
        enabled, forced = flags[t]
        assert enabled is True, f"{t}: RLS no habilitada"
        assert forced is True, f"{t}: RLS no forzada (force row level security falta)"


def test_hardening_indexes_exist():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    expected = {"idx_triage_verdicts_failure", "idx_actions_verdict",
                "idx_triage_corrections_family", "idx_test_runs_commit", "idx_certificates_org"}
    with psycopg.connect(DBURL) as conn, conn.cursor() as cur:
        cur.execute("select indexname from pg_indexes where schemaname='public' and indexname = any(%s)",
                    (list(expected),))
        found = {r[0] for r in cur.fetchall()}
    assert expected <= found, f"faltan índices: {expected - found}"
```

- [ ] **Step 4: Run, expect PASS** (the migration was applied in Step 2)

Run: `python3 -m pytest tests/test_migration_016_rls.py -q` → PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add db/migrations/016_hardening.sql tests/test_migration_016_rls.py
git commit -m "fix(security): migración 016 — force RLS en tablas base + índices FK + is_org_member hoist + ivfflat parciales

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: B3 — idempotencia de ingesta (`ON CONFLICT`)

**Files:** Modify `src/defects/repository.py` (`ingest_ci_run`, ~250-274); Test `tests/test_ci_ingestion_idempotency.py` (or extend the existing CI ingestion repo test file).

**Interfaces:** Consumes — el índice único parcial `idx_test_runs_run_uid (org_id, run_uid) where run_uid is not null` (migración 008). Produces — `ingest_ci_run` idempotente sin race.

- [ ] **Step 1: Write the failing integration test** — `tests/test_ci_ingestion_idempotency.py`:

```python
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

from src.defects.repository import AssuranceRepository

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def org():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user_id = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s, %s, 'authenticated', 'authenticated', now(), now())",
                        (user_id, f"dedup-{user_id[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("dedup-org-" + user_id[:8], user_id))
            org_id = str(cur.fetchone()[0])
        conn.commit()
    yield {"user_id": user_id, "org_id": org_id}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id=%s", (org_id,))
            cur.execute("delete from auth.users where id=%s", (user_id,))
        conn.commit()


def test_same_run_uid_dedups_without_error(org):
    repo = AssuranceRepository(DBURL)
    ruid = "run-" + uuid.uuid4().hex
    args = dict(user_id=org["user_id"], org_id=org["org_id"], project="web",
                source="playwright", commit_sha="sha1", run_uid=ruid,
                items=[], results=[], snapshots=[])
    first = repo.ingest_ci_run(**args)
    second = repo.ingest_ci_run(**args)   # misma entrega — NO debe lanzar UniqueViolation
    assert second["deduplicated"] is True
    assert second["run_id"] == first["run_id"]
```

(Match the real `ingest_ci_run` signature when reading the method; adjust kwarg names if they differ.)

- [ ] **Step 2: Run, expect FAIL or current-behavior**

Run: `python3 -m pytest tests/test_ci_ingestion_idempotency.py -q`. (With the current check-then-insert this passes sequentially; the fix makes it robust under the concurrent path. If it already passes, proceed — the value is the regression guard + the ON CONFLICT change below.)

- [ ] **Step 3: Implement the `ON CONFLICT` change** in `src/defects/repository.py` `ingest_ci_run`. Replace the check-then-insert block (the `if run_uid is not None: select … existing …` lookup at ~250-267 **and** the unconditional `insert … returning id` at ~269-274) with an atomic upsert:

```python
                if run_uid is not None:
                    cur.execute(
                        "insert into public.test_runs (org_id, project, source, commit_sha, run_uid)"
                        " values (%s, %s, %s, %s, %s)"
                        " on conflict (org_id, run_uid) where run_uid is not null do nothing"
                        " returning id",
                        (org_id, project, source, commit_sha, run_uid),
                    )
                    inserted = cur.fetchone()
                    if inserted is None:
                        # entrega duplicada concurrente o reintento → devolver el run existente
                        cur.execute(
                            "select id, summary from public.test_runs"
                            " where org_id = %s and run_uid = %s",
                            (org_id, run_uid),
                        )
                        existing = cur.fetchone()
                        summary = (existing["summary"] if existing else None) or {}
                        return {
                            "run_id": str(existing["id"]),
                            "ingested": summary.get("ingested", 0),
                            "known": summary.get("known", 0),
                            "novel": summary.get("novel", 0),
                            "results_recorded": summary.get("results_recorded", 0),
                            "snapshots_saved": summary.get("snapshots_saved", 0),
                            "deduplicated": True,
                        }
                    run_id = inserted["id"]
                else:
                    cur.execute(
                        "insert into public.test_runs (org_id, project, source, commit_sha, run_uid)"
                        " values (%s, %s, %s, %s, %s) returning id",
                        (org_id, project, source, commit_sha, run_uid),
                    )
                    run_id = cur.fetchone()["id"]
```

(The membership check above this block stays. The `for item in items` / results / snapshots loops below stay unchanged — they only run when a row was actually inserted.)

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_ci_ingestion_idempotency.py -q` → PASS. Then `python3 -m pytest -m "not integration" -q` → stays green.

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py tests/test_ci_ingestion_idempotency.py
git commit -m "fix(ingesta): dedup idempotente con INSERT ON CONFLICT (run_uid) — sin 502 en concurrencia

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: A3 (métrica del foso honesta) + A4 (sin familia duplicada por centroid NULL)

**Files:** Modify `src/defects/repository.py` (`set_family_label` ~822-860, `_query_candidates` ~60-97, y el mapeo de `FamilyCandidate`); Test: extend `tests/test_triage_repository.py`.

**Interfaces:** Consumes — `triage_verdicts.llm_assisted`, `triage_corrections`. Produces — `engine_category` = `"unknown"` cuando el último veredicto fue `llm_assisted`; `_query_candidates` devuelve la familia de firma exacta aunque `centroid` sea NULL.

- [ ] **Step 1: A3 — `engine_category` honesto.** In `set_family_label`, change the recent-verdict query to also fetch `llm_assisted`, and derive `engine_category`:

```python
                if org_id is not None:
                    cur.execute(
                        "select tv.category, tv.llm_assisted from public.triage_verdicts tv"
                        " join public.failures f on f.id = tv.failure_id"
                        " where f.defect_family_id = %s order by tv.created_at desc limit 1",
                        (family_id,),
                    )
                    er = cur.fetchone()
                    engine_category = (
                        ("unknown" if er["llm_assisted"] else er["category"]) if er else None
                    )
                    cur.execute(
                        "insert into public.triage_corrections"
                        " (org_id, family_id, engine_category, human_category, source, reason, corrected_by)"
                        " values (%s, %s, %s, %s, 'family_label', %s, %s)",
                        (org_id, family_id, engine_category, label, reason, user_id),
                    )
```

- [ ] **Step 2: A4 — firma exacta sin filtro de centroide.** In `_query_candidates`, remove `and centroid is not null` from the OUTER `where` (keep it only inside the top-K subquery), and make the row mapping tolerate a NULL centroid:

```python
        cur.execute(
            """
            select id, signature, centroid
            from public.defect_families
            where scope = 'org' and org_id = %(org)s
              and (
                  signature = %(fp)s
                  or id in (
                      select id from public.defect_families
                      where scope = 'org' and org_id = %(org)s and centroid is not null
                      order by centroid <=> %(emb)s
                      limit %(k)s
                  )
              )
            """,
            {"org": org_id, "fp": fingerprint, "emb": Vector(list(embedding)), "k": limit},
        )
        rows = cur.fetchall()
        return [
            FamilyCandidate(
                family_id=str(r["id"]),
                signature=r["signature"],
                centroid=list(r["centroid"]) if r["centroid"] is not None else None,
            )
            for r in rows
        ]
```

Then check `src/defects/match.py`: `FamilyCandidate.centroid` must accept `None` (make it `Optional[List[float]]` with default `None` if it isn't already), and confirm `decide_match` resolves an exact-signature match WITHOUT dereferencing `centroid` (the signature match must win before any cosine math). If `decide_match` uses `centroid` for the exact-signature path, guard it so a NULL centroid still returns that family. (Read the file; adjust only what's needed for the NULL-centroid exact match.)

- [ ] **Step 3: Write the integration tests** — append to `tests/test_triage_repository.py` (reuse its existing org/family seeding fixture; it already tests `set_family_label`). Two tests:

```python
@pytest.mark.integration
def test_engine_category_is_unknown_when_llm_assisted(assurance_repo, seeded_family):
    # seeded_family debe permitir crear un veredicto; si el fixture ya siembra uno,
    # crea/actualiza uno con llm_assisted=True y category!='real'.
    repo, ctx = assurance_repo, seeded_family
    _set_recent_verdict(ctx, category="flaky", llm_assisted=True)   # helper local: inserta tv del fallo de la familia
    repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"], label="real", reason="r")
    row = _last_correction(ctx["family_id"])                        # helper local: SELECT de triage_corrections
    assert row["engine_category"] == "unknown"   # el motor fue ambiguo; el LLM decidió
    assert row["human_category"] == "real" and row["reason"] == "r"
    assert row["source"] == "family_label" and str(row["corrected_by"]) == ctx["user_id"]


@pytest.mark.integration
def test_engine_category_is_verdict_when_not_llm(assurance_repo, seeded_family):
    repo, ctx = assurance_repo, seeded_family
    _set_recent_verdict(ctx, category="real", llm_assisted=False)
    repo.set_family_label(user_id=ctx["user_id"], family_id=ctx["family_id"], label="real")
    assert _last_correction(ctx["family_id"])["engine_category"] == "real"
```

Add the small helpers `_set_recent_verdict(ctx, *, category, llm_assisted)` (INSERT a `triage_verdicts` row for a failure of `ctx["family_id"]` — reuse/extend the fixture's seeded failure; set `rule_applied`, `confidence`, `requires_approval`, `status`, `evidence_bundle={}`) and `_last_correction(family_id)` (SELECT the most recent `triage_corrections` row for the family, `dict_row`). If the existing fixture doesn't expose a failure id, extend it to seed one failure linked to the family (mirror `test_certify_repository.py`'s seeding).

For A4, add a unit-ish integration test that inserts a `defect_families` row with the same `(org_id, signature)` but `centroid = NULL`, then calls `repo._query_candidates(cur, org_id=…, fingerprint=<that signature>, embedding=[0.0]*384)` and asserts the family is returned (so a re-ingest matches it instead of creating a duplicate that would hit `uq_defect_families_org_signature`).

- [ ] **Step 4: Run, expect PASS**

Run: `python3 -m pytest tests/test_triage_repository.py -q` → PASS. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/defects/repository.py src/defects/match.py tests/test_triage_repository.py
git commit -m "fix(triaje): métrica del foso mide el motor (no el LLM) + firma exacta sin filtro de centroide

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **B3 y la concurrencia real:** el test cubre el caso de reentrega (mismo `run_uid` → dedup sin excepción). El `ON CONFLICT` lo hace atómico (la versión vieja podía dar `UniqueViolation`→502 bajo dos entregas simultáneas).
- **A4 toca `match.py`:** el cambio principal es en `_query_candidates`, pero `FamilyCandidate`/`decide_match` deben tolerar `centroid=None` para la rama de firma exacta — verificarlo al implementar.
- **Despliegue:** `016` ya se aplica a la BD en Task 1. El índice único `uq_defect_families_org_signature` (003) sigue siendo la red de seguridad de A4 a nivel de BD.
- **Fuera de alcance:** PR-B (authz admin, atomicidad de acciones, anti-injection GitHub).
