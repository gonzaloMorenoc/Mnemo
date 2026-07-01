# Rendimiento · Pool de conexiones + frontend optimista — diseño

**Fecha:** 2026-07-01 · **Base:** `main` 9277c4d (con `maxDuration=60`) · **Backend:** Python/FastAPI/psycopg · **Frontend:** Next.js/TS.

## Objetivo

Bajar la latencia por request y que `/v2/orgs` deje de bloquear toda la app. Del análisis de rendimiento: (3) el backend abre una conexión nueva a Supabase en **cada** request (`psycopg.connect` → SSL handshake al pooler de eu-central-1 → 1–8 s/request) y (4) el `OrgProvider` gatea la app entera esperando `/v2/orgs`. Este trabajo ataca ambos, **a 0 €** (sin cambiar de hosting). El cold start (pinger) y el hardware quedan fuera.

## Decisiones (confirmadas en el análisis)

- **Pool de conexiones** en el backend (reusar conexiones en vez de abrir una por request).
- **Frontend optimista**: usar el `activeOrgId` guardado sin esperar a `/v2/orgs`.
- **Sin romper la multitenancy**: el membership app-layer sigue; el pooler de Supabase ya bypassa RLS; los claims son `set_config(..., is_local=true)` (transaction-scoped → no contaminan una conexión reusada).
- **Mismo API de los repos** (cambio mínimo, sin reescribir queries).

## Componentes

### 1. Pool global (`src/db/pool.py`, nuevo)
Un `psycopg_pool.ConnectionPool` singleton, lazy:
```python
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector
from src.config import DATABASE_URL

_pool: ConnectionPool | None = None

def _configure(conn):
    conn.row_factory = dict_row
    register_vector(conn)          # pgvector, una vez por conexión del pool

def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL, min_size=2, max_size=10,
            open=False, configure=_configure, timeout=10,
            kwargs={"row_factory": dict_row},
        )
        _pool.open(wait=True, timeout=15)
    return _pool

def close_pool():
    global _pool
    if _pool is not None:
        _pool.close(); _pool = None
```
- `min_size=2` pre-abre 2 conexiones (el connect lento se paga aquí, no por request). `max_size=10` para concurrencia.
- `configure` corre por conexión NUEVA del pool → `row_factory` + `register_vector` centralizados.
- Requiere `DATABASE_URL`; si falta, `get_pool()` lanza (igual que hoy sin BD).

### 2. Repos: `_connect` usa el pool
Cada `_connect` pasa de abrir una conexión a **tomarla del pool**:
```python
def _connect(self):
    return get_pool().connection()   # context manager: checkout → commit/rollback → return-to-pool
```
`with self._connect() as conn:` **no cambia** (mismo API; antes commit+close, ahora commit+return-to-pool). Se **elimina** el `register_vector(conn)` y el `row_factory=dict_row` inline de los repos (ya en el pool `configure`). `_set_claims`/`_set_user_claims` se mantienen igual (transaction-local). Afecta: `orgs`, `defects`, `knowledge`, `certify`, `jira/integrations_repository`, `graph/service`, `repo_ingest`; y `graph/gaps._connect` (función de módulo → misma sustitución).

### 3. Dependencia + arranque
- `requirements.txt`: `psycopg[binary]==3.3.3` → `psycopg[binary,pool]==3.3.3` (añade `psycopg_pool`).
- `asgi.py`: un **lifespan** que pre-abre el pool al startup y lo cierra al shutdown, para que el contenedor arranque con el pool caliente (no el primer request):
```python
from contextlib import asynccontextmanager
from src.db.pool import get_pool, close_pool

@asynccontextmanager
async def lifespan(app):
    try: get_pool()          # pre-calienta; si la BD no está, degradar sin tumbar el arranque
    except Exception: pass
    yield
    close_pool()
app = FastAPI(title="Mnemo Autopilot", version="2.0.0", lifespan=lifespan)
```

### 4. Frontend: `OrgProvider` optimista (`org-provider.tsx`)
- Leer el `activeOrgId` de `localStorage` en el **primer render** y usarlo aunque `/v2/orgs` aún no haya respondido → las páginas (con `enabled: accessToken && orgId`) arrancan sus queries de inmediato.
- Cuando `orgsQuery` resuelve, **validar**: si el `activeOrgId` guardado no está en la lista, corregir a `orgs[0].id`.
- `staleTime` largo para la query de orgs (`5 * 60_000`; cambian poco).
- Fórmula: `activeOrgId = explicitOrgId || storedOrgId || (orgs[0]?.id ?? "")`, con la validación al cargar `orgs`.

## Garantías
- **Multitenancy intacta**: el pool no cambia el membership app-layer ni los claims transaction-local; el pooler ya bypassa RLS. Sin estado compartido entre checkouts (claims local + `pool.connection()` hace rollback de transacción abierta al devolver).
- **Mismo comportamiento**: `with self._connect() as conn:` sigue haciendo commit al salir; las queries no cambian.
- **Degrada**: si el pool no abre (BD caída), los endpoints fallan igual que hoy; el lifespan no tumba el arranque.
- **Impacto**: connect por request de 1–8 s → ~0 (reuso) → requests <0,3 s una vez caliente.

## Testing
- **Backend** (`tests/test_db_pool.py`, nuevo): el pool devuelve conexiones con `dict_row`; reusa (el mismo pool en 2 `get_pool()`); `configure` aplica register_vector (mock/psycopg fake); dos checkouts consecutivos no comparten claims (el 2º no ve `request.jwt.claim.sub` del 1º). Los tests de repos existentes deben seguir verdes (el API de `_connect` no cambia; mockear `get_pool().connection()` donde haga falta). `pytest -m "not integration"` sin `.env`.
- **Frontend** (vitest): `OrgProvider` expone el `activeOrgId` de localStorage antes de que `getOrganizations` resuelva; tras resolver con una lista que no contiene el guardado, corrige a `orgs[0]`.
- **Verificación local = CI** por tarea (backend sin `.env`; frontend `lint:ci`+`test`+`build`).

## Fuera de alcance
- Cold start (pinger), hardware persistente, mover de host.
- Reescribir los repos a un ORM o cambiar las queries.
- Pool en el proxy de Vercel (es serverless; no aplica).
