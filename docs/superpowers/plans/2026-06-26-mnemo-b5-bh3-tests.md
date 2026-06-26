# Bloque B.5 · BH3 — Tests/verificación — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Probar el aislamiento multi-tenant a nivel de policy Postgres (no solo flags) y medir la cobertura en CI con un umbral que falle ante regresiones.

**Architecture:** T1 añade un test de integración que conmuta al rol `authenticated` + claims y verifica que un tenant no ve filas de otro; T2 instrumenta `pytest-cov` en el paso de CI con `--cov-fail-under` medido.

**Tech Stack:** Python/pytest, psycopg, Supabase Postgres RLS, GitHub Actions.

## Global Constraints

- **RLS conductual:** el test simula el rol `authenticated` (`set role authenticated`) + el claim del usuario (`request.jwt.claim.sub`) para que las policies (`is_org_member`/`auth.uid()`) apliquen — NO usa el bypass del pooler. Es la garantía que vende el producto.
- **Cobertura:** `--cov=src --cov-fail-under=N`, con `N` MEDIDO y puesto justo por debajo de la real (no romper hoy; fallar a futuro).
- `DATABASE_URL`=prod (integración con cleanup en fixture, orgs/usuarios efímeros, CASCADE). `python3 -m pytest`. Commits terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: RLS conductual (org-A no ve org-B a nivel de policy)

**Files:** Test `tests/test_rls_behavioral.py`.

**Contexto técnico (verificado):** `_set_claims` hace `set_config('request.jwt.claim.sub', user_id, true)` + `set_config('request.jwt.claim.role','authenticated', true)` pero NO `set role` → con el rol del pooler (bypass) RLS no aplica. Las policies usan `auth.uid()` (que en Supabase lee `request.jwt.claim.sub`) vía `is_org_member(org_id)`. Para ejercitar RLS, el test debe `set role authenticated` antes de los selects (y `reset role` después). El seed se hace ANTES, con el rol del pooler (bypass), para poder insertar en ambas orgs.

- [ ] **Step 1: Write the failing test** — `tests/test_rls_behavioral.py`:

```python
import os
import uuid

import psycopg
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.integration
load_dotenv()

DBURL = os.getenv("DATABASE_URL", "")


@pytest.fixture
def two_orgs():
    if not DBURL:
        pytest.skip("DATABASE_URL not configured")
    user_b = str(uuid.uuid4())
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("insert into auth.users (id, email, role, aud, created_at, updated_at)"
                        " values (%s,%s,'authenticated','authenticated',now(),now())",
                        (user_b, f"rls-{user_b[:8]}@test.internal"))
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("rls-A-" + user_b[:8], user_b))   # created_by no implica que user_b sea miembro de A
            org_a = str(cur.fetchone()[0])
            cur.execute("insert into public.organizations (name, created_by) values (%s,%s) returning id",
                        ("rls-B-" + user_b[:8], user_b))
            org_b = str(cur.fetchone()[0])
            # user_b es miembro SOLO de B; sacarlo de A si el trigger de created_by lo añadió
            cur.execute("delete from public.memberships where org_id=%s and user_id=%s", (org_a, user_b))
            cur.execute("insert into public.memberships (org_id, user_id, role) values (%s,%s,'member')"
                        " on conflict (org_id, user_id) do update set role='member'", (org_b, user_b))
            # una familia de defectos en CADA org (seed con el rol del pooler = bypass)
            for org, sig in ((org_a, "sig-A"), (org_b, "sig-B")):
                cur.execute("insert into public.defect_families (org_id, scope, signature, title)"
                            " values (%s,'org',%s,%s)", (org, sig, "t-" + sig))
        conn.commit()
    yield {"user_b": user_b, "org_a": org_a, "org_b": org_b}
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from public.organizations where id in (%s,%s)", (org_a, org_b))
            cur.execute("delete from auth.users where id=%s", (user_b))
        conn.commit()


def _count_families_as(user_id, org_id):
    """Cuenta familias de una org BAJO EL ROL authenticated + el claim del usuario (RLS activa)."""
    with psycopg.connect(DBURL) as conn:
        with conn.cursor() as cur:
            cur.execute("set role authenticated")
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (user_id,))
            cur.execute("select set_config('request.jwt.claim.role', 'authenticated', true)")
            cur.execute("select count(*) from public.defect_families where org_id = %s", (org_id,))
            n = cur.fetchone()[0]
            cur.execute("reset role")
            return n


def test_member_of_b_cannot_read_org_a_rows(two_orgs):
    ctx = two_orgs
    # control positivo: user_b SÍ ve su org B
    assert _count_families_as(ctx["user_b"], ctx["org_b"]) >= 1
    # aislamiento: user_b NO ve la org A a nivel de policy Postgres
    assert _count_families_as(ctx["user_b"], ctx["org_a"]) == 0
```

(IMPORTANT for the implementer: this depends on Supabase specifics. Before asserting, VERIFY the claim plumbing actually drives `auth.uid()`: after `set role authenticated` + the `set_config`, run `select auth.uid()` and confirm it returns `user_b`. If `auth.uid()` reads `request.jwt.claims` (JSON) instead of `request.jwt.claim.sub`, set BOTH: `select set_config('request.jwt.claims', json_build_object('sub', %s, 'role','authenticated')::text, true)`. Also confirm `defect_families` has an RLS policy referencing `is_org_member`/`auth.uid()` — check its migration; if `defect_families` isn't a good probe table, use `certificates` or another tenant table that has the policy. The binding assertion is: member-of-B reads 0 rows of A and ≥1 of B under the `authenticated` role. If `set role authenticated` is not permitted from the pooler role, report BLOCKED with the exact error — do NOT fall back to a bypass connection that would make the test vacuous.)

- [ ] **Step 2: Run, expect the right RED→GREEN** — `python3 -m pytest tests/test_rls_behavioral.py -q`. This test should PASS once written IF the RLS policies are correct (it's a characterization test of existing behavior). If it FAILS with org-A count > 0, that's a REAL RLS hole — STOP and report it as a finding (do not weaken the test).

- [ ] **Step 3: (no production code)** — this task adds only the test. If Step 2 revealed a real hole, escalate; otherwise the policies already enforce isolation and the test now proves it.

- [ ] **Step 4: Confirm** — `python3 -m pytest tests/test_rls_behavioral.py -q` → PASS. Then `python3 -m pytest -m "not integration" -q` → green (this test is integration-marked, so it's deselected there — that's expected).

- [ ] **Step 5: Commit**

```bash
git add tests/test_rls_behavioral.py
git commit -m "test(rls): aislamiento conductual cross-tenant a nivel de policy Postgres

Demuestra (bajo rol authenticated + claim) que un miembro de la org B lee 0 filas
de la org A y >=1 de la suya. Cierra el gap de la auditoría (antes solo flags).

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: Cobertura medida en CI (`--cov-fail-under`)

**Files:** Modify `requirements.txt` (añadir `pytest-cov`), `.github/workflows/backend-ci.yml` (el paso de pytest). Posible: `pyproject.toml`/`setup.cfg` si conviene fijar `[tool.coverage.run] omit`.

- [ ] **Step 1: Medir la cobertura actual.** Asegúrate de tener `pytest-cov` (si no, `pip install pytest-cov`), y corre:

```bash
python3 -m pytest -m "not integration" --cov=src --cov-report=term-missing -q | tail -30
```

Anota el porcentaje TOTAL (la última línea `TOTAL ... NN%`). Llámalo `R`. El umbral será `N = floor(R) - 3` (margen para no romper por fluctuaciones). Documenta `R` y `N` en el mensaje de commit.

- [ ] **Step 2: Añadir `pytest-cov` a `requirements.txt`.** Usa una versión compatible con `pytest==9.0.2` (p.ej. `pytest-cov==7.0.0`; verifica que instala y corre):

```
pytest-cov==7.0.0
```

- [ ] **Step 3: Instrumentar el paso de CI.** En `.github/workflows/backend-ci.yml`, cambiar el paso (línea ~39) de:

```yaml
        run: python -m pytest -m "not integration" -q
```
a (sustituye `N` por el número calculado en el Step 1):

```yaml
        run: python -m pytest -m "not integration" --cov=src --cov-report=term-missing --cov-fail-under=N -q
```

- [ ] **Step 4: Verificar localmente que el gate pasa con el N elegido**:

```bash
python3 -m pytest -m "not integration" --cov=src --cov-fail-under=N -q | tail -5
```
Expected: exit 0 (la cobertura real `R` ≥ `N`). Si falla, baja `N` 1-2 puntos (no subas la cobertura en este PR — eso es trabajo aparte).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .github/workflows/backend-ci.yml
git commit -m "ci: medir cobertura con pytest-cov y fallar el build bajo el umbral (R=<R>%, N=<N>%)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **T1 es un test de caracterización:** si pasa, prueba que el aislamiento RLS ya funciona (y lo blinda contra regresiones futuras); si falla, ha encontrado un agujero real — eso es una victoria de la auditoría, no un fallo del plan. NO debilitar el test para que pase.
- **T1 es el backstop a nivel de BD del authz de BH2** (que se aplica en la capa de app porque el pooler bypassa RLS).
- **T2 no sube la cobertura** — solo la mide y pone el gate. Subirla es trabajo posterior.
- **Fuera de alcance:** H2 (arranque e2e), God-objects, Bloque C; subir la cobertura por encima del 80%.
