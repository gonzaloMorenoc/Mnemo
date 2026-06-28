# QA Continuity AI · G1 (Ingesta del repositorio) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Indexar los tests existentes del repo del cliente (vía la GitHub App) en una tabla `test_assets`, disparado desde `/app/integrations`.

**Architecture:** T1 `list_tree` en GitHubCodeHost. T2 tabla + repo. T3 servicio de indexación. T4 endpoints. T5 cliente. T6 UI.

**Tech Stack:** Python/FastAPI/pytest · Postgres/pgvector · GitHub API · Next.js/TS/vitest.

## Global Constraints

- **Determinista (sin LLM):** la indexación es listar + leer + embeddings. No usa `generate_structured`.
- **Multi-tenant (el pooler bypassa RLS):** `test_assets` con RLS+force+policy `is_org_member`; TODA query filtra `org_id` y comprueba `_is_member` ANTES de leer/escribir (patrón `src/knowledge/repository.py`).
- **Estilo implícito:** se guardan los tests; NO se genera un "perfil". (G5 los usará como few-shot.)
- **Cotas:** máx **200** ficheros, máx **100 000** bytes por fichero; full-replace por repo.
- **Verificación local = CI por tarea:** frontend `npm run lint:ci` + `test` + `tsc` + `build`; backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= python3 -m pytest -m "not integration" -q; mv .env.bak .env`). **No usar git worktree** (trabajar en la rama). Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: `GitHubCodeHost.list_tree` + filtro de tests

**Files:** Modify `src/ci/github_app.py`; Test `tests/test_github_app_list_tree.py`.

**Interfaces:** Produces — `GitHubCodeHost.list_tree() -> list[str]`; `is_test_path(path: str) -> bool` (módulo).

- [ ] **Step 1: Write the failing test** (mock `_session` como en los tests de github_app): `list_tree` hace GET a `…/git/trees/{sha}?recursive=1` y devuelve solo los `path` de `type=="blob"`; `is_test_path` acepta `e2e/login.spec.ts`, `tests/x.test.ts`, `features/a.feature`, `cypress/b.cy.ts` y rechaza `src/app.ts`, `README.md`.

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** en `src/ci/github_app.py`:

```python
_TEST_EXTS = (".spec.ts", ".test.ts", ".spec.js", ".test.js", ".feature", ".cy.ts", ".cy.js")
_TEST_DIRS = ("tests/", "test/", "e2e/", "cypress/", "specs/", "__tests__/", "features/")


def is_test_path(path: str) -> bool:
    p = path.lower()
    if p.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js", ".feature", ".cy.ts", ".cy.js")):
        return True
    return any(d in p for d in _TEST_DIRS) and p.endswith((".ts", ".js", ".feature"))
```
y como método de `GitHubCodeHost`:
```python
def list_tree(self) -> List[str]:
    """Rutas de todos los ficheros del repo (rama por defecto). Lanza GitHubError en fallo."""
    sha = self._ref_sha(self._default_branch())
    resp = self._session.get(f"{_API}/repos/{self._repo}/git/trees/{sha}",
                             params={"recursive": "1"}, headers=self._headers(), timeout=30)
    if resp.status_code >= 300:
        raise GitHubError(f"get tree falló: HTTP {resp.status_code}")
    return [it["path"] for it in resp.json().get("tree", []) if it.get("type") == "blob"]
```

- [ ] **Step 4: Run PASS** + backend-no-`.env` gate green. **Step 5: Commit** `feat(github): list_tree + is_test_path (listar tests del repo)` + trailer.

---

## Task 2: Tabla `test_assets` (migración 020, a prod) + `TestAssetRepository`

**Files:** Create `db/migrations/020_test_assets.sql`, `src/repo_ingest/__init__.py`, `src/repo_ingest/repository.py`; Test `tests/test_test_assets_repo.py`, `tests/test_test_assets_rls.py`.

**Interfaces:** Produces — `TestAssetRepository` con `replace_for_repo(*, user_id, org_id, repo, assets) -> int`, `list_assets(*, user_id, org_id) -> list[dict]`, `search_semantic(*, user_id, org_id, query_embedding, k=5) -> list[dict]`. `assets` = `list[{path, framework, domain, content}]`.

- [ ] **Step 1: Migración** `db/migrations/020_test_assets.sql` (plantilla de `018_qa_knowledge.sql`):
```sql
create table if not exists public.test_assets (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    repo_full_name text not null,
    path text not null,
    framework text,
    domain text,
    content text not null,
    embedding vector(384),
    created_at timestamptz not null default now()
);
create index if not exists idx_test_assets_org on public.test_assets (org_id);
create index if not exists idx_test_assets_domain on public.test_assets (org_id, domain) where domain is not null;
create index if not exists idx_test_assets_embedding on public.test_assets
    using ivfflat (embedding vector_cosine_ops) with (lists = 100) where embedding is not null;
alter table public.test_assets enable row level security;
alter table public.test_assets force row level security;
create policy test_assets_member on public.test_assets
    using (public.is_org_member(org_id)) with check (public.is_org_member(org_id));
```
- [ ] **Step 2: Aplicar a prod** (atómico, restaura `.env`):
```bash
cd /Users/gonzalo/Documents/GitHub/Mnemo
export DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'')
psql "$DATABASE_URL" -f db/migrations/020_test_assets.sql
psql "$DATABASE_URL" -tAc "select relrowsecurity, relforcerowsecurity from pg_class where relname='test_assets';"  # debe ser t | t
```
- [ ] **Step 3: Implement** `src/repo_ingest/repository.py` (clon de `QaKnowledgeRepository`): `_connect` (`dict_row`+`register_vector`), `_is_member`, `replace_for_repo` (membership; `delete … where org_id=%s and repo_full_name=%s`; luego `insert` por asset con `Vector(list(self.embedder.embed(a["content"][:8000])))`; `conn.commit()`; devuelve el nº insertado; no-miembro → 0 sin escribir), `list_assets` (select `path, framework, domain` por org), `search_semantic` (cosine `embedding <=> %s`, para G5).
- [ ] **Step 4: Tests** — `tests/test_test_assets_repo.py` (embedder fake; membership: no-miembro → 0 / `[]`; replace borra+inserta); `tests/test_test_assets_rls.py` (marker `integration`, patrón de los tests RLS existentes: un no-miembro no ve filas de otro org). Run el repo test sin `.env` + el RLS con `.env`.
- [ ] **Step 5: Commit** `feat(repo-ingest): tabla test_assets (RLS, migración 020) + TestAssetRepository` + trailer.

---

## Task 3: Servicio de indexación `index_repo_tests`

**Files:** Create `src/repo_ingest/service.py`; Test `tests/test_repo_ingest_service.py`.

**Interfaces:** Consumes — `GitHubCodeHost.list_tree`/`read_file` (T1), `is_test_path` (T1), `TestAssetRepository.replace_for_repo` (T2). Produces — `index_repo_tests(*, user_id, org_id, repo, codehost, asset_repo) -> dict` (`{indexed, by_domain, skipped}`).

- [ ] **Step 1: Write the failing test**: un `codehost` fake cuyo `list_tree` devuelve `["e2e/login.spec.ts", "src/app.ts", "features/billing.feature"]` y `read_file` devuelve contenido; un `asset_repo` fake → `index_repo_tests` filtra a los 2 tests, infiere `framework` (`playwright`/`cucumber`), `domain` del path, y llama `replace_for_repo` con 2 assets; un fichero > 100 KB → `skipped`; devuelve `{indexed:2, by_domain:{...}, skipped:…}`.

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** `src/repo_ingest/service.py`:
```python
from collections import Counter
from typing import Any, Dict
from src.ci.github_app import is_test_path

_MAX_FILES = 200
_MAX_BYTES = 100_000


def _framework(path: str) -> str:
    p = path.lower()
    if p.endswith(".feature"):
        return "cucumber"
    if ".cy." in p:
        return "cypress"
    return "playwright"


def _domain(path: str) -> str:
    parts = [s for s in path.lower().split("/") if s not in
             ("tests", "test", "e2e", "cypress", "specs", "__tests__", "features", "src")]
    return parts[0] if len(parts) > 1 else "general"


def index_repo_tests(*, user_id: str, org_id: str, repo: str, codehost, asset_repo) -> Dict[str, Any]:
    paths = [p for p in codehost.list_tree() if is_test_path(p)][:_MAX_FILES]
    assets, skipped = [], 0
    for p in paths:
        content = codehost.read_file(p)
        if not content or len(content.encode("utf-8")) > _MAX_BYTES:
            skipped += 1
            continue
        assets.append({"path": p, "framework": _framework(p), "domain": _domain(p), "content": content})
    asset_repo.replace_for_repo(user_id=user_id, org_id=org_id, repo=repo, assets=assets)
    return {"indexed": len(assets), "by_domain": dict(Counter(a["domain"] for a in assets)), "skipped": skipped}
```

- [ ] **Step 4: Run PASS** + backend-no-`.env` gate. **Step 5: Commit** `feat(repo-ingest): index_repo_tests (lista+filtra+lee+indexa, determinista)` + trailer.

---

## Task 4: Endpoints `/v2/repo/*`

**Files:** Modify `src/api_v2.py`, `src/multitenant_models.py`; Test `tests/test_api_v2_repo.py`.

- [ ] **Step 1: Model** (`multitenant_models.py`): `class RepoIndexRequest(BaseModel): org_id: str`.
- [ ] **Step 2: Endpoints** (`src/api_v2.py`):
```python
from src.repo_ingest.service import index_repo_tests
from src.repo_ingest.repository import TestAssetRepository

@router.post("/repo/index", response_model=Dict[str, Any])
def repo_index(req: RepoIndexRequest, user: AuthenticatedUser = Depends(get_current_user)) -> Dict[str, Any]:
    cfg = get_integrations_repo().get_github_config(user_id=user.user_id, org_id=req.org_id)  # membership-gated; repo_full_name
    if not cfg.get("configured") or not cfg.get("repo_full_name"):
        raise HTTPException(status_code=503, detail="GitHub no configurado para el org")
    try:
        host = _github_codehost_factory(req.org_id, user.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="No es miembro de la organización") from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return index_repo_tests(user_id=user.user_id, org_id=req.org_id,
                                repo=cfg["repo_full_name"], codehost=host, asset_repo=TestAssetRepository())
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/repo/tests", response_model=List[Dict[str, Any]])
def repo_tests(org_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> List[Dict[str, Any]]:
    return TestAssetRepository().list_assets(user_id=user.user_id, org_id=org_id)
```
(`get_github_config` ya comprueba membership y lanza `PermissionError` para no-miembro — confírmalo y deja que propague a 403, o mapéalo aquí.)
- [ ] **Step 3: Tests** (`tests/test_api_v2_repo.py`, `dependency_overrides` + monkeypatch `api_v2.index_repo_tests`/`TestAssetRepository`/`get_integrations_repo`): index → 200 `{indexed,…}`; **401 sin auth**; **503 sin config GitHub**; 403 no-miembro; `/repo/tests` → lista.
- [ ] **Step 4: Run PASS** + backend-no-`.env` gate. **Step 5: Commit** `feat(api): endpoints /v2/repo/index + /v2/repo/tests` + trailer.

---

## Task 5: Cliente frontend

**Files:** Modify `frontend/src/lib/api/endpoints.ts`, `types.ts`; Test `frontend/src/lib/api/__tests__/repo.test.ts`.

- [ ] **Step 1: Type** (`types.ts`): `TestAsset` ({ path: string; framework: string; domain: string }); `RepoIndexResult` ({ indexed: number; by_domain: Record<string, number>; skipped: number }).
- [ ] **Step 2: Client** (`endpoints.ts`):
```ts
export function indexRepo(token: string, body: { org_id: string }) {
  return apiRequest<RepoIndexResult>("/api/v2/repo/index", "POST", { token, body });
}
export function listRepoTests(token: string, params: { org_id: string }) {
  return apiRequest<TestAsset[]>(`/api/v2/repo/tests?org_id=${encodeURIComponent(params.org_id)}`, "GET", { token });
}
```
- [ ] **Step 3: Test** (`__tests__/repo.test.ts`, `global.fetch` spy): `indexRepo` postea a `/api/v2/repo/index`; `listRepoTests` GET con `org_id`. Run `npm test -- repo` + lint:ci + tsc. **Commit** + trailer.

---

## Task 6: UI en `/app/integrations`

**Files:** Modify `frontend/src/app/app/integrations/page.tsx`, its test.

- [ ] **Step 1: UI.** Junto a la config de GitHub: un botón **"Indexar tests del repo"** → `useMutation(indexRepo)` con `{ org_id: activeOrgId }`; on success → `toast.success("N tests indexados")` + refrescar `useQuery(listRepoTests)`; muestra la lista (`path` · `framework` · `domain`) y un resumen por dominio. Si GitHub no está configurado → el botón deshabilitado + aviso "configura GitHub primero". Degrada: error → `toast.error` (503 → "Configura GitHub"). Usa `useActiveOrg` (+ `isLoading`).
- [ ] **Step 2: Test** (vitest, mock auth + `useActiveOrg` + endpoints): con GitHub configurado, click en "Indexar tests del repo" llama `indexRepo` y muestra el resultado; `listRepoTests` renderiza un test; sin config → botón deshabilitado/aviso; error → toast.
- [ ] **Step 3: Run** `npm run lint:ci` + `npm test` + `tsc` + `build`. **Commit** + trailer.

---

## Notas de cierre
- **Orden:** T1 → T2 (migración a prod) → T3 → T4 → T5 → T6. T3 consume T1+T2; T4 consume T3; T6 consume T5.
- **Reusa:** `GitHubCodeHost`, el patrón repo/embedding de `qa_knowledge`, `LocalEmbedder`, `_github_codehost_factory`, la página integrations.
- **Determinista:** sin LLM; degrada (sin GitHub → 503; fichero ilegible → skip).
- **Migración 020 a prod** en T2; **verificación local=CI** en cada tarea (Global Constraints).
- **Fuera de alcance:** código fuente/PRs, coverage gap real (G2), automation desde el estilo (G5), incremental.
