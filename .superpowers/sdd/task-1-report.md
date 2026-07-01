# Task 1 Report — Pool global de conexiones (`src/db/pool.py`) — feat/mnemo-perf-connpool

## Status: DONE

---

## Files Created / Modified

| File | Action |
|------|--------|
| `requirements.txt` | Modified: `psycopg[binary]==3.3.3` → `psycopg[binary,pool]==3.3.3` |
| `src/db/__init__.py` | Created: empty package marker |
| `src/db/pool.py` | Created: `get_pool`, `close_pool`, `_configure` |
| `tests/test_db_pool.py` | Created: 2 unit tests (TDD RED→GREEN) |

---

## Dependency change

`requirements.txt` line 24:
```
-psycopg[binary]==3.3.3
+psycopg[binary,pool]==3.3.3
```
Installed via `python3 -m pip install -q "psycopg[binary,pool]==3.3.3"` (already satisfied — the pool extra was already present in the virtual environment; no other package version changes).

---

## `src/db/pool.py`

Verbatim from brief:

- `_pool: Optional[ConnectionPool] = None` — module-level singleton state.
- `_configure(conn)` — called once per new pool connection; sets `conn.row_factory = dict_row` and calls `register_vector(conn)`. Centralizes both concerns so repos never need to repeat them.
- `get_pool()` — lazy init: if `_pool is None`, creates a `ConnectionPool` with `min_size=2, max_size=10, open=False`, then calls `pool.open(wait=True, timeout=15)`. Pre-opens 2 connections at startup (slow SSL handshake paid once). Returns the singleton.
- `close_pool()` — closes and nulls the singleton (used in tests and graceful shutdown).

Key design: `kwargs={"row_factory": dict_row}` is passed both via `configure=_configure` (per-connection) and as a `kwargs` default, ensuring dict rows even if `configure` is skipped in any psycopg_pool code path.

---

## `_configure` — why both dict_row and register_vector here

`psycopg_pool.ConnectionPool` calls `configure(conn)` after each new connection is established and before it is handed to the caller. This is the correct hook for:
1. `conn.row_factory = dict_row` — ensures every cursor on this connection returns `dict`s.
2. `register_vector(conn)` — registers pgvector's custom OID mapping so `vector` columns deserialize correctly.

Centralizing both in `_configure` means repos (Tasks 2–3) can call `pool.connection()` and get a ready-to-use connection without any per-call setup.

---

## Tests (`tests/test_db_pool.py`)

### `test_get_pool_is_singleton`
Monkeypatches `ConnectionPool` with `FakePool` and resets `_pool = None`. Calls `get_pool()` twice, asserts:
- `p1 is p2` — same object returned (singleton)
- `len(created) == 1` — constructor called exactly once

### `test_configure_sets_dict_row_and_vector`
Monkeypatches `register_vector` to count calls. Calls `_configure(Conn())`. Asserts:
- `c.row_factory is dict_row` — row factory set correctly
- `calls["vector"] == 1` — `register_vector` called exactly once

TDD cycle: RED (`ModuleNotFoundError: No module named 'src.db'`) → GREEN after creating `src/db/__init__.py` and `src/db/pool.py`.

---

## pytest Results

```
tests/test_db_pool.py: 2 passed in 0.41s
```

---

## no-.env Gate

Command (atomically):
```
cd /Users/gonzalo/Documents/GitHub/Mnemo && mv .env .env.bak 2>/dev/null; DATABASE_URL= python3 -m pytest -m "not integration" -q; rc=$?; mv .env.bak .env 2>/dev/null; echo "rc=$rc env=$(ls -la .env 2>/dev/null|awk '{print $5}')"
```

Result:
```
819 passed, 105 deselected, 1 warning in 37.43s
rc=0 env=1167
```

`.env` restored (1167 bytes). All non-integration tests pass including the 2 new pool tests.

---

## Commit

Subject: `feat(db): pool de conexiones global (psycopg_pool)`
Branch: `feat/mnemo-perf-connpool`
Trailer: `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`

---

## Concerns

1. **`get_pool()` blocks at startup**: `pool.open(wait=True, timeout=15)` opens `min_size=2` connections synchronously. This means the first call to `get_pool()` will block for the SSL handshake duration (1–8 s per connection). Tasks 2–3 should call `get_pool()` at app lifespan startup (not inside a request handler) to pay this cost once at boot.

2. **`DATABASE_URL` empty in no-.env mode**: When `DATABASE_URL=""` (no-.env gate), `get_pool()` would fail if called (ConnectionPool with empty conninfo). The tests monkeypatch `ConnectionPool` so this is not an issue for the test suite. The integration callers (Tasks 2–3) are marked `integration` and skipped in the no-.env gate.

3. **`kwargs={"row_factory": dict_row}` may overlap with `configure`**: Both `configure` and `kwargs` set dict_row. This is intentional double-coverage; `configure` is the authoritative path and `kwargs` is a belt-and-suspenders fallback for psycopg_pool internals.

4. **pgvector OID registration per connection**: `register_vector` registers the vector type on the specific connection's OID cache. With a pool, this must be done for each new connection — `configure` is the correct hook for this. Verified by the test.
