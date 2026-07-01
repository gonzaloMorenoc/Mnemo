# Rendimiento · Pool de conexiones + frontend optimista — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reusar conexiones a Postgres (pool) para eliminar el connect de 1–8 s por request, y que `/v2/orgs` no bloquee la carga de la app.

**Architecture:** T1 crea un pool global (`src/db/pool.py`). T2 migra los `_connect` de los repos a `pool.connection()`. T3 pre-calienta el pool en el arranque (lifespan). T4 hace el `OrgProvider` optimista.

**Tech Stack:** Python/FastAPI/psycopg 3.3 + psycopg_pool · Next.js/TS · vitest.

## Global Constraints

- **Pool lazy singleton**; `configure` centraliza `row_factory=dict_row` + `register_vector` (idempotente, para todas las conexiones aunque el repo no use pgvector).
- **Mismo API de los repos**: `_connect()` sigue usándose como `with self._connect() as conn:` (ahora devuelve `pool.connection()`: commit al salir + return-to-pool).
- **No tocar** `_set_claims`/`_set_user_claims` (son `set_config(..., is_local=true)` transaction-local; se limpian al commit → no fugan entre checkouts).
- **Multitenancy intacta**: el membership app-layer y el bypass RLS del pooler no cambian.
- `psycopg[binary,pool]==3.3.3` (misma versión, +extra pool). `register_vector` = `from pgvector.psycopg import register_vector`.
- **Verificación local = CI por tarea:** backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= python3 -m pytest -m "not integration" -q; mv .env.bak .env`); frontend `npm run lint:ci`+`test`+`build`. Si node_modules se corrompe (iCloud) → `npm --prefix frontend ci`. **No git worktree.** Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Pool global (`src/db/pool.py`) + dependencia

**Files:** Create `src/db/__init__.py` (vacío si no existe), `src/db/pool.py`; Modify `requirements.txt`; Test `tests/test_db_pool.py`.

**Interfaces:** Produces — `get_pool() -> ConnectionPool`, `close_pool() -> None`. `get_pool().connection()` es un context manager que da una `psycopg.Connection` con `row_factory=dict_row` y vector registrado.

- [ ] **Step 1: Dependency** — en `requirements.txt`, cambiar `psycopg[binary]==3.3.3` por `psycopg[binary,pool]==3.3.3`. Instalar: `python3 -m pip install -q "psycopg[binary,pool]==3.3.3"`.

- [ ] **Step 2: Write the failing test** (`tests/test_db_pool.py`):
```python
import src.db.pool as poolmod

def test_get_pool_is_singleton(monkeypatch):
    created = []
    class FakePool:
        def __init__(self, *a, **k): created.append(k)
        def open(self, **k): pass
        def close(self): pass
    monkeypatch.setattr(poolmod, "ConnectionPool", FakePool)
    monkeypatch.setattr(poolmod, "_pool", None)
    p1 = poolmod.get_pool(); p2 = poolmod.get_pool()
    assert p1 is p2                       # singleton
    assert len(created) == 1              # se crea una sola vez
    poolmod.close_pool()

def test_configure_sets_dict_row_and_vector(monkeypatch):
    calls = {"vector": 0}
    monkeypatch.setattr(poolmod, "register_vector", lambda conn: calls.__setitem__("vector", calls["vector"]+1))
    class Conn: row_factory = None
    c = Conn()
    poolmod._configure(c)
    from psycopg.rows import dict_row
    assert c.row_factory is dict_row
    assert calls["vector"] == 1
```

- [ ] **Step 3: Run, expect FAIL.** `python3 -m pytest tests/test_db_pool.py -q`

- [ ] **Step 4: Implement** `src/db/pool.py`:
```python
from typing import Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector

from src.config import DATABASE_URL

_pool: Optional[ConnectionPool] = None


def _configure(conn) -> None:
    conn.row_factory = dict_row
    register_vector(conn)


def get_pool() -> ConnectionPool:
    """Pool global lazy. Pre-abre min_size conexiones (el connect lento se paga aquí)."""
    global _pool
    if _pool is None:
        pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=2,
            max_size=10,
            open=False,
            timeout=10,
            configure=_configure,
            kwargs={"row_factory": dict_row},
        )
        pool.open(wait=True, timeout=15)
        _pool = pool
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
```
(Si `pgvector.psycopg.register_vector` requiere una conexión ya con el tipo disponible, el `configure` es el sitio correcto — corre una vez por conexión nueva del pool.)

- [ ] **Step 5: Run PASS** + backend-no-`.env` gate (rc=0, `.env` restaurado). **Commit** `feat(db): pool de conexiones global (psycopg_pool)` + trailer.

---

## Task 2: Migrar los repos al pool

**Files:** Modify `src/orgs/repository.py`, `src/certify/repository.py`, `src/jira/integrations_repository.py`, `src/graph/service.py`, `src/defects/repository.py`, `src/knowledge/repository.py`, `src/repo_ingest/repository.py`, `src/graph/gaps.py`; Tests: la suite existente de cada uno.

**Interfaces:** Consumes — `get_pool` de `src/db/pool.py` (Task 1).

- [ ] **Step 1** — En cada repo, importar `from src.db.pool import get_pool` y reemplazar el cuerpo de `_connect`:
  - Repos **sin** pgvector (`orgs`, `certify`, `jira/integrations_repository`):
    ```python
    def _connect(self):
        return get_pool().connection()
    ```
    (elimina `psycopg.connect(self.db_url, row_factory=dict_row)`).
  - Repos **con** pgvector (`graph/service`, `defects`, `knowledge`, `repo_ingest`): igual que arriba, y **eliminar** las 2 líneas inline `conn = psycopg.connect(..., row_factory=dict_row)` + `register_vector(conn)` (ahora en el `configure` del pool). Quitar el import `register_vector` si queda sin uso; **mantener** `from pgvector import Vector` (se usa en las queries).
  - `src/graph/gaps.py::_connect(db_url=DATABASE_URL)` (función de módulo):
    ```python
    def _connect(db_url: str = DATABASE_URL):
        return get_pool().connection()
    ```
    (el pool usa `DATABASE_URL` global; el parámetro `db_url` queda por compatibilidad de firma pero el pool lo ignora).

- [ ] **Step 2** — `self.db_url` puede quedar sin uso en algunos repos; déjalo (lo usan otros métodos o el `__init__`) salvo que quede claramente muerto. No cambies las queries ni `_set_claims`.

- [ ] **Step 3: Run the backend suite** (sin `.env`): `mv .env .env.bak 2>/dev/null; DATABASE_URL= python3 -m pytest -m "not integration" -q; rc=$?; mv .env.bak .env 2>/dev/null; echo rc=$rc`. **Ajusta los tests que rompan**: los que parcheaban `psycopg.connect` a nivel de módulo del repo ahora deben parchear `<repo>.get_pool` (o el `_connect` del repo) para devolver un context manager fake que dé la conexión mock. Los que ya parchean `_connect` directamente siguen igual. Objetivo: rc=0.

- [ ] **Step 4: Commit** `refactor(repos): _connect usa el pool global (reuso de conexión)` + trailer.

---

## Task 3: Pre-calentar el pool en el arranque (`asgi.py`)

**Files:** Modify `asgi.py`.

- [ ] **Step 1: Implement** — añadir un `lifespan` y pasarlo a `FastAPI`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.api_v2 import router as v2_router
from src.db.pool import get_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_pool()          # pre-calienta el pool; si la BD no está, no tumbar el arranque
    except Exception:
        pass
    yield
    close_pool()


app = FastAPI(title="Mnemo Autopilot", version="2.0.0", lifespan=lifespan)
app.include_router(v2_router)
```

- [ ] **Step 2: Verify** — `python3 -c "import asgi"` sin error; backend-no-`.env` gate rc=0 (el `try/except` evita que la ausencia de BD en el import rompa). **Commit** `perf(asgi): pre-calienta el pool en el arranque (lifespan)` + trailer.

---

## Task 4: `OrgProvider` optimista (frontend)

**Files:** Modify `frontend/src/components/providers/org-provider.tsx`; Test `frontend/src/components/providers/__tests__/org-provider.test.tsx`.

- [ ] **Step 1: Write the failing test** (vitest): mock `useAuth`→`{accessToken:"t"}` y `getOrganizations`. (a) con `localStorage["mnemo.activeOrgId"]="org-guardada"` y `getOrganizations` pendiente (promesa no resuelta), un componente que consume `useActiveOrg().activeOrgId` muestra `"org-guardada"` **antes** de que resuelva. (b) cuando `getOrganizations` resuelve con `[{id:"org-otra",...}]` (no contiene la guardada), `activeOrgId` pasa a `"org-otra"` (corrección).

- [ ] **Step 2: Implement** — en `org-provider.tsx`, leer el guardado y usarlo optimista + validar al cargar:
```tsx
const orgsQuery = useQuery({
  queryKey: ["organizations", accessToken],
  queryFn: () => getOrganizations(accessToken!),
  enabled: Boolean(accessToken),
  staleTime: 5 * 60_000,
});
const orgs = useMemo(() => orgsQuery.data ?? [], [orgsQuery.data]);

const storedOrgId = typeof window !== "undefined"
  ? window.localStorage.getItem(STORAGE_KEY) ?? ""
  : "";

const activeOrgId = useMemo(() => {
  if (explicitOrgId) return explicitOrgId;
  if (orgs.length) {
    return orgs.some((o) => o.id === storedOrgId) ? storedOrgId : orgs[0].id;  // validación
  }
  return storedOrgId;   // optimista: aún no cargó la lista
}, [explicitOrgId, orgs, storedOrgId]);
```
Mantener `setActiveOrgId` (escribe en localStorage) y `isLoading: orgsQuery.isLoading`.

- [ ] **Step 3: Verify** — `npm run lint:ci` + `npm test` + `npx tsc --noEmit` + `npm run build`. **Commit** `perf(frontend): OrgProvider optimista (no bloquea la app en /v2/orgs)` + trailer.

---

## Notas de cierre
- **Orden:** T1 (pool) → T2 (repos usan get_pool) → T3 (lifespan usa get_pool) → T4 (frontend, independiente).
- **Riesgo principal (T2):** los tests que parchean `psycopg.connect`. La mitigación es parchear `get_pool`/`_connect` en su lugar; el gate sin `.env` lo caza.
- **Reusa:** `register_vector`/`dict_row` (ahora en el pool), el patrón `with self._connect()`, `useQuery`/localStorage.
- **Impacto esperado:** connect por request 1–8 s → ~0 (reuso) tras el arranque caliente; la app deja de esperar a `/v2/orgs`.
- **Fuera de alcance:** cold start (pinger), hardware, mover de host.
