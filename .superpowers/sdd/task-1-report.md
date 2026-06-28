# Task 1 Report — Coverage Gap Detector (regla_sin_test) — feat/mnemo-g2-coverage-gap

## Status: DONE

---

## New gap kinds

| Kind | Trigger | Severity |
|------|---------|----------|
| `regla_sin_test` | `qa_knowledge` with `kind in (regla_negocio, flujo, riesgo)` whose cosine distance to nearest `test_asset` > 0.55 (or `best_dist IS NULL`) | `alta` for `riesgo`, `media` otherwise |
| `repo_no_indexado` | `count(test_assets) == 0` for the org | `media` (fixed, no LLM call) |

## Cross SQL

`_SQL_REGLA_SIN_TEST` performs a correlated scalar subquery: for each `qa_knowledge` row with an embedding, it computes `min(k.embedding <=> t.embedding)` across all `test_assets` of the same `org_id` that have a non-null embedding. The result (`best_dist`) is compared to `_COVERAGE_THRESHOLD = 0.55`. Multi-tenant: both tables are filtered by `org_id` inside the `_is_member`-gated block.

## Threshold

`_COVERAGE_THRESHOLD = 0.55` (cosine distance, declared as module-level constant for calibration). Values below = covered (no gap); values >= threshold or `NULL` = uncovered (gap emitted).

## Zero-tests branch

When `count(test_assets) == 0`, the cross-query is skipped entirely — no `regla_sin_test` gaps emitted. Exactly one `repo_no_indexado` gap is appended with `_FALLBACK_REC["repo_no_indexado"]` (fixed, no LLM call). Prevents false positives on orgs that haven't indexed their repo yet.

## Tests added (15 new tests across 3 classes)

Mock pattern update: `_make_conn_ctx` now uses `fetchone.side_effect = [{"ok": member}, {"n": n_tests}]` to support two sequential `fetchone` calls (membership check + test count). All existing 23 tests continue to pass unmodified.

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestReglaSinTest` | 8 | near test (dist<0.55) → no gap; regla_negocio far → media; riesgo far → alta; `best_dist=None` → gap; affected=[knowledge id]; LLM rec used; LLM None → `_FALLBACK_REC["regla_sin_test"]`; required fields |
| `TestRepoNoIndexado` | 6 | exactly 1 gap; no `regla_sin_test`; severity media; affected=[]; non-empty rec; required fields |
| `TestCoverageGapNonMember` | 1 | non-member → [] even when n_tests>0 |

## no-.env gate

`rc=0`, `.env` restored (1167 bytes). 799 non-integration tests pass.

## Commit

`feat(graph): coverage gap real (regla_sin_test cruzando qa_knowledge × test_assets)`

## Concerns

1. **Correlated subquery performance**: `_SQL_REGLA_SIN_TEST` runs one `min(<=>)` scan per `qa_knowledge` row. For large orgs, a LATERAL join or CTE would be more efficient. Acceptable for MVP.
2. **`best_dist` = NULL when n_tests > 0 but all embeddings are NULL**: The count gate checks `count(test_assets)` (rows, not embeddings), so if rows exist but none have embeddings, `best_dist` is NULL per row → treated as uncovered (gap emitted). Correct but potentially noisy; worth a log/warning in future.
3. **`n_tests` scope**: The variable is assigned inside the `with` block and read after it. Python scope handles this correctly but is a mild code smell for future refactors.

---

# Task 1 Report — list_tree + is_test_path — feat/mnemo-g1-repo-ingest

## Status: DONE

---

## Implementation

### `is_test_path(path: str) -> bool` — module-level in `src/ci/github_app.py`

Added immediately after `_API` constant. Two module-level constants:
- `_TEST_EXTS`: tuple of test extensions (`.spec.ts`, `.test.ts`, `.spec.js`, `.test.js`, `.feature`, `.cy.ts`, `.cy.js`)
- `_TEST_DIRS`: tuple of test directory prefixes (`tests/`, `test/`, `e2e/`, `cypress/`, `specs/`, `__tests__/`, `features/`)

Logic: returns `True` if path ends with a test extension (checked on lowercased path), OR if it contains a test directory AND ends with `.ts`, `.js`, or `.feature`.

### `GitHubCodeHost.list_tree() -> List[str]` — method in `GitHubCodeHost`

Added after `read_file`. Reuses `_default_branch()` + `_ref_sha()` helpers. Issues a single GET to `/repos/{repo}/git/trees/{sha}?recursive=1`, raises `GitHubError` on `status_code >= 300`, returns only `path` values where `type == "blob"`.

## Tests — `tests/test_github_app_list_tree.py`

16 tests, all passing (same `_Resp`/`_host` mock pattern as `test_github_app_read_file.py`):

| Test | Validates |
|------|-----------|
| `test_list_tree_gets_trees_endpoint_with_recursive` | GET issued to correct URL with `params={"recursive": "1"}` |
| `test_list_tree_returns_only_blob_paths` | tree-type entries are filtered out; only blobs returned |
| `test_list_tree_raises_on_non_2xx` | `GitHubError` raised on HTTP 403 |
| `test_list_tree_empty_tree` | returns `[]` when tree list is empty |
| `test_is_test_path_accepts_test_paths[*]` | 7 cases: `e2e/login.spec.ts`, `tests/x.test.ts`, `features/a.feature`, `cypress/b.cy.ts`, `src/__tests__/utils.ts`, `specs/payment.spec.js`, `test/helpers.js` |
| `test_is_test_path_rejects_non_test_paths[*]` | 5 cases: `src/app.ts`, `README.md`, `package.json`, `src/utils/helper.ts`, `docs/architecture.md` |

## no-.env Gate

```
737 passed, 96 deselected in 12.60s
rc=0 env=1167
```

`.env` fully restored (1167 bytes). All non-integration tests pass.

## Commit

TBD (see reply).

## Concerns

1. `_TEST_EXTS` constant is defined but not directly referenced inside `is_test_path` — the function inlines the same tuple in `endswith()`. Kept verbatim per brief; the constant documents intent.
2. `list_tree` does not handle GitHub's truncated tree responses (repos with >100k objects get `truncated: true` in the response). Not in scope for Task 1 but worth noting for production hardening.

---

# Task 1 Report — GraphService.build_graph — feat/mnemo-qa-graph

## Status
DONE. All 10 unit tests pass. backend-no-`.env` gate: rc=0, `.env` restored.

## Files Created
- `src/graph/__init__.py` — empty package init
- `src/graph/service.py` — GraphService with `_connect`, `_is_member`, `build_graph`
- `tests/test_graph_service.py` — 10 unit tests (no DB required)

## Implementation Notes

`GraphService` mirrors `knowledge/repository.py` exactly:
- `_connect`: `psycopg.connect(self.db_url, row_factory=dict_row)` + `register_vector(conn)`
- `_is_member`: `select exists(select 1 from public.memberships ...)` before any data access
- Non-member returns `{"nodes": [], "edges": []}` immediately

Graph construction (all in-memory after two SQL queries):
1. Fetch `qa_knowledge` rows for `org_id` up to `limit`
2. Collect `defect_family_id` values; if any, fetch matching `defect_families` (org or global)
3. Build nodes: `knowledge` (one per row), `defect` (one per unique fam), `domain` (one per unique domain value)
4. Build edges: `documenta` (knowledge→defect), `pertenece` (knowledge→domain), `tag` (knowledge↔knowledge sharing a tag)
5. If `focus` given, keep only that node + its direct neighbors, trim edges to the keep-set

`defect_families` schema confirmed: no `domain` column (id/scope/org_id/signature/title/root_cause/status/occurrence_count/centroid). Query fetches only `id, title, occurrence_count`.

## Test Summary (10 unit tests)
- `TestBuildGraphNonMember`: non-member → `{nodes:[], edges:[]}`
- `TestBuildGraphNodeCounts`: 2 knowledge + 1 defect + 1 domain nodes
- `TestBuildGraphEdges`: `documenta`, `pertenece` (×2), `tag` edges correct
- `TestBuildGraphLimit`: limit param wired to SQL; 1 row → 1 knowledge node; execute call verified
- `TestBuildGraphFocus`: focus=K2 keeps K2+domain+K1(tag), excludes F1; focus=K1 keeps K1+F1+domain+K2; documenta edge excluded when focus=K2
- `TestBuildGraphNoDefectFamilies`: when no `defect_family_id`, only 2 execute calls (no second fetchall)

Mock pattern: `_make_conn_ctx` returns a `(conn_ctx, conn, cur)` triple identical to the `knowledge/repository` test helper. `cur.fetchall.side_effect` consumes a list so first call returns knowledge rows, second returns defect rows.

## no-.env Gate
```
mv .env .env.bak 2>/dev/null; DATABASE_URL= python3 -m pytest -m "not integration" -q; rc=$?; mv .env.bak .env 2>/dev/null
rc=0 env=1167
```
686 passed, 96 deselected (integration tests skipped). `.env` restored (1167 bytes).

## Commit
`036b864` — `feat(graph): build_graph deriva el grafo de conocimiento (qa_knowledge + defect_families)`

## Self-Review
- Pattern mirrors `knowledge/repository.py` exactly (diff is only the domain/tag/focus logic)
- `add_node` helper prevents duplicate nodes for shared domains/defects
- `focus` filter is O(n) over edges — acceptable at limit=200
- Tag edges are O(k²) per tag bucket; bounded by `limit`
- Immutable: `nodes` dict replaced with filtered copy; `edges` replaced with filtered list

## Concerns
1. `defect_families` second query uses `any(%s::uuid[])` with a Python list — psycopg3 accepts `list[str]` for `any(...)` cast; strings come from `id::text` so are valid UUIDs (safe)
2. Similarity edges (`relation:"similar"`) deferred intentionally per brief to avoid N top-k embedding queries
3. No pagination for the graph — `limit` caps `qa_knowledge` rows; dense tag buckets could still produce many edges (max ~limit²/2), acceptable for current scope
4. `focus` node absent from DB — if caller passes a non-existent ID, result is `{nodes:[], edges:[]}` (keep-set empty). Silent but correct.

---

# Task 1 Report — Automation Agent (generate_playwright_test) — feat/mnemo-qa-continuity-automation

## Status: DONE

---

## Files Created

- `src/automation/__init__.py` — empty package marker
- `src/automation/agent.py` — `_slug`, `_case_text`, `_fallback`, `generate_playwright_test` (49 lines)
- `tests/test_automation_agent.py` — 18 unit tests

## Implementation Notes

`src/automation/agent.py` is verbatim from the brief (mirrors `ai_repair.py` / `testplan/agent.py`):
- `_TEST_SCHEMA = {"code": "", "filename": "", "notes": ""}` — structured output shape
- `_slug(title)` — converts case title to kebab-case filename stem
- `_case_text(case)` — renders `gherkin` (priority) or `steps` list to plain text for the prompt context
- `_fallback(case)` — returns a `test.fixme()` skeleton with case as `// comments`; notes say "LLM no disponible"; never raises
- `generate_playwright_test(*, case, style_sample=None, provider=None)` — builds `context` list; appends `style_sample` entry (id="style_sample") only when given; calls `generate_structured(..., on_failure="none")`; type-guards `code`, `filename`, `notes`; degrades to `_fallback` if `res is None` or `code` is empty/whitespace

No tweaks were needed — the brief's code passed all 18 tests as-is.

## Test Coverage

| Test | Scenario | Result |
|------|----------|--------|
| `test_returns_llm_code_and_filename_when_llm_succeeds` | LLM response → code/filename/notes returned | PASS |
| `test_style_sample_included_in_context_when_given` | style_sample provided → id="style_sample" in context | PASS |
| `test_style_sample_absent_from_context_when_not_given` | style_sample=None → no style_sample in context | PASS |
| `test_prompt_mentions_imita_when_style_sample_given` | prompt includes "imita" when style given | PASS |
| `test_prompt_uses_standard_conventions_when_no_style_sample` | prompt mentions "convenciones"/"estándar" when no style | PASS |
| `test_gherkin_case_is_included_in_context` | gherkin case → gherkin text in context id="case" | PASS |
| `test_steps_case_is_included_in_context` | steps case → steps in context id="case" | PASS |
| `test_degrades_to_fallback_when_llm_returns_none` | LLM→None → fallback dict, non-empty code, .spec.ts filename | PASS |
| `test_fallback_code_contains_case_title` | fallback code includes case title | PASS |
| `test_fallback_code_contains_fixme` | fallback code contains test.fixme() | PASS |
| `test_fallback_notes_mentions_llm_unavailable` | fallback notes mention "LLM" / "no disponible" | PASS |
| `test_degrades_when_llm_returns_empty_code` | LLM returns whitespace code → fallback | PASS |
| `test_fallback_works_for_gherkin_case` | gherkin case fallback: title in code, correct filename | PASS |
| `test_fallback_works_for_steps_case` | steps case fallback: title in code, correct filename | PASS |
| `test_never_raises_on_none_case` | case=None → no raise, returns valid dict | PASS |
| `test_filename_fallback_when_llm_returns_bad_filename` | LLM returns blank filename → derived from title | PASS |
| `test_notes_defaults_to_empty_string_when_llm_returns_non_string` | LLM notes=42 → "" | PASS |
| `test_on_failure_none_passed_to_generate_structured` | on_failure="none" verified in call kwargs | PASS |

## pytest Results

```
tests/test_automation_agent.py: 18 passed in 0.05s
Full suite (-m "not integration"): 647 passed, 96 deselected in 27.45s
```

TDD cycle: RED (ModuleNotFoundError before creating agent.py) → GREEN after implementation.

## Self-Review

- Code is verbatim from brief; no tweaks were required.
- Type-guards on `code`, `filename`, `notes` match `ai_repair.py` pattern.
- `_fallback` never raises; `generate_playwright_test` degrades gracefully.
- `on_failure="none"` means `generate_structured` absorbs LLM errors; `None` result triggers fallback explicitly.
- `style_sample` is truncated to `_MAX=6000` chars before passing to context.
- Immutable: all functions return new dicts, no mutation.
- Files are small: `agent.py` 49 lines, test file 170 lines.

## Concerns

None blocking. Minor notes:
- No outer `try/except` in `generate_playwright_test` (same as `testplan/agent.py`; `ai_repair.py` wraps in try/except but it's a class method). `generate_structured(on_failure="none")` guarantees no LLM exceptions; `_case_text` and `_fallback` are too simple to fail.
- `case=None` is coerced to `{}` at the top of the function — safe.

---

# Task 1 Report — Onboarding Agent (summarize_domain + learning_path)

## Status: DONE

---

## Files Created
- `src/onboarding/__init__.py` — empty package marker
- `src/onboarding/agent.py` — `_gather`, `summarize_domain`, `learning_path` (44 lines)
- `tests/test_onboarding_agent.py` — 7 unit tests

## Implementation Notes

`src/onboarding/agent.py` mirrors `testplan/agent.py` exactly per brief:
- Shared `_gather(knowledge_service, user_id, org_id, topic)` calls `search_unified(query=topic, k=8)` and returns `(sources, context)`.
- `summarize_domain` → `generate_structured(..., schema=_SUMMARY_SCHEMA, on_failure="none")` → type-guards all 6 list fields → fallback (res is None) returns empty lists + citations = top-8 source ids.
- `learning_path` → `generate_structured(..., schema=_PATH_SCHEMA, on_failure="none")` → type-guards `days` and `citations` → fallback returns 1-day hint + source ids.
- Code is verbatim from brief; no tweaks needed.

## Test Coverage

| Test | Scenario | Result |
|------|----------|--------|
| `test_summarize_domain_returns_all_fields_with_citations` | LLM returns dict → all 6 keys, both source ids in citations | PASS |
| `test_summarize_domain_degrades_when_llm_returns_none` | LLM→None → fallback with all keys, source ids cited | PASS |
| `test_summarize_domain_normalizes_bad_types` | LLM returns `rules="not a list", citations=42` → coerced to `[]` | PASS |
| `test_learning_path_returns_days_with_citations` | LLM returns dict → days list (3 items), source ids cited | PASS |
| `test_learning_path_degrades_when_llm_returns_none` | LLM→None → fallback day with item, source ids cited | PASS |
| `test_learning_path_normalizes_bad_types` | LLM returns `days="not a list", citations=None` → coerced to `[]` | PASS |
| `test_gather_passes_topic_as_query` | `_gather` forwards topic as query with k=8 | PASS |

## pytest Results

```
tests/test_onboarding_agent.py: 7 passed in 0.03s
Full suite (-m "not integration"): 619 passed, 96 deselected in 15.81s
```

TDD cycle: RED (ModuleNotFoundError before implementation) → GREEN after.

## Commit

SHA: `a6aae6a`
Subject: `feat(onboarding): agentes summarize_domain + learning_path (citan la memoria)`
Branch: `feat/mnemo-qa-continuity-onboarding`

## Self-Review
- Code is idiomatic Python; immutable (returns new dicts, no mutation).
- Type-guards on every list field; fallback never raises.
- `_gather` is DRY — both agents reuse it.
- `on_failure="none"` means `generate_structured` absorbs LLM errors; both agents handle None explicitly.
- Files are small (agent.py 44 lines, test file 100 lines).

## Concerns
1. **`_SUMMARY_SCHEMA` and `_PATH_SCHEMA` use `()` (empty tuples)** as sentinel values — same pattern as `testplan/agent.py`. The actual returned fields are always lists via type-guards.
2. **No named `_fallback` function** — brief inlines fallback logic in each function (vs. testplan which extracts it). Both patterns are equivalent; kept verbatim from brief.
3. **Provider param** passes through to `generate_structured` untouched — enables Haiku/Sonnet/Opus selection at call site.

---

# Task 1 Report — Test Plan Agent (núcleo) — Fase 1b

## Status: DONE

---

## Files Created

- `src/testplan/__init__.py` — empty package init
- `src/testplan/agent.py` — `generate_test_plan` implementation (~30 lines)
- `tests/test_testplan_agent.py` — 6 unit tests

## Implementation Notes

`src/testplan/agent.py` mirrors `briefing.py` exactly:
- `generate_structured(..., on_failure="none")` → LLM failure returns `None` → `_fallback(sources)` called.
- `_fallback` returns all schema keys defaulted to `[]`, plus `citations` = source ids and a `gaps` notice.
- `context` is built as `[{id, content}]` from `search_unified` results.
- `case_format` is threaded into the prompt string: `fmt` variable selects manual (`steps:[]` wording) vs. gherkin (`Given-When-Then` wording).

**One minimal tweak vs. the brief's verbatim code:** added `out["citations"] = out["citations"] if isinstance(out["citations"], list) else []` after the `summary` guard. The brief only normalizes `summary`; `briefing.py` explicitly normalizes every field. Without this guard, the normalization test failed (string `"x"` passed through unchanged). This matches the spirit of the brief ("mirror `briefing.py`") since `briefing.py` normalizes all its output fields.

## Test Coverage

| Test | Scenario | Result |
|------|----------|--------|
| `test_generate_test_plan_returns_plan_with_citations` | LLM returns plan dict → citations contain both source ids | PASS |
| `test_generate_test_plan_degrades_when_llm_returns_none` | LLM→None → fallback: citations=source ids, gaps non-empty, no raise | PASS |
| `test_generate_test_plan_threads_gherkin_format_into_prompt` | `case_format="gherkin"` → "gherkin" in prompt | PASS |
| `test_generate_test_plan_threads_manual_format_into_prompt` | default `case_format="manual"` → "manual"/"steps" in prompt | PASS |
| `test_generate_test_plan_normalizes_bad_types` | LLM returns `summary=42, citations="x"` → coerced to `str`/`list` | PASS |
| `test_generate_test_plan_never_raises_on_exception` | LLM→None path is safe (no exception propagates) | PASS |

## pytest Results

```
tests/test_testplan_agent.py: 6 passed in 0.03s
Full suite (-m "not integration"): 546 passed, 96 deselected in 15.30s
```

## Self-Review

- Code is idiomatic Python, follows immutability (no mutation, new dicts returned).
- All type guards present; fallback never raises.
- `case_format` is threaded exactly as specified; both formats verified by tests.
- No hardcoded secrets; no side effects.
- Files are small (agent.py ~30 lines, test file ~100 lines).

## Concerns

None blocking. The one adaptation (citations normalization) is a strict improvement that matches the existing `briefing.py` pattern and was caught by a defensive test. The brief's verbatim code works for all other fields.

---

## Previous task-1 report content (Fase 1a — kept for history)

## Status: DONE

---

## Migration file

**Path:** `db/migrations/018_qa_knowledge.sql`

Contains verbatim SQL from brief:
- `create extension if not exists vector;`
- Table `public.qa_knowledge` with all 7-value kind check, all fields, `domain`, `source default 'manual'`, `confidence` check, optional `defect_family_id`/`run_id`, `embedding vector(384)`
- 3 indices: `idx_qa_knowledge_org`, `idx_qa_knowledge_domain` (partial, domain not null), `idx_qa_knowledge_embedding` (ivfflat partial, embedding not null)
- RLS: `enable row level security`, `force row level security`, policy `qa_knowledge_member` using `public.is_org_member(org_id)`

## psql apply output

```
psql:db/migrations/018_qa_knowledge.sql:1: NOTICE:  extension "vector" already exists, skipping
CREATE EXTENSION
CREATE TABLE
CREATE INDEX
CREATE INDEX
psql:db/migrations/018_qa_knowledge.sql:26: NOTICE:  ivfflat index created with little data
DETAIL:  This will cause low recall.
HINT:  Drop the index until the table has more data.
CREATE INDEX
ALTER TABLE
ALTER TABLE
CREATE POLICY
```

All DDL statements succeeded. The "little data" notice on ivfflat is expected for an empty table.

## RLS verification

```sql
select relrowsecurity, relforcerowsecurity from pg_class where relname='qa_knowledge';
```

Result: `t | t` — both enable and force are active.

## Test file

**Path:** `tests/test_qa_knowledge_rls.py`

Two integration tests (`@pytest.mark.integration`):
1. `test_qa_knowledge_rls_enabled_and_forced` — queries `pg_class`, asserts `relrowsecurity=True` and `relforcerowsecurity=True`
2. `test_qa_knowledge_member_policy_exists` — queries `pg_policies`, asserts `qa_knowledge_member` is present

**Run result:** `2 passed in 0.76s`

## Commit (QA Continuity Fase 1a)

SHA: `c0ee98c`
Subject: `feat(knowledge): tabla qa_knowledge + RLS (Fase 1a memoria)`
Branch: `feat/mnemo-qa-continuity`
Files committed: `db/migrations/018_qa_knowledge.sql`, `tests/test_qa_knowledge_rls.py`

## Concerns

1. **ivfflat with empty table**: Postgres emits a low-recall warning on the embedding index because the table has no data yet. This is expected and harmless — the index will work correctly once rows are inserted.
2. **gen_random_uuid()**: No errors — the function is available without needing `pgcrypto` (Postgres 13+ has it natively).
3. **No FK on `created_by`**: The `created_by uuid not null` field has no foreign key (matches brief verbatim). If a FK to `auth.users` or `profiles` is desired, it should be added in a subsequent migration.

---

## Previous report content (C4 Demo — kept for history)

## Commit
`f1c9557` — feat(demo): green baseline de test_perfil → el push en vivo da R3 maintenance (self-heal)

---

## Files Created / Modified

### 1. `scripts/demo_fixtures/perfil_green.json` (created)

```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-perfil-baseline", "source": "playwright",
 "tests": [{"test_name": "test_perfil", "status": "pass",
            "dom": "<form id=\"perfil\"><button id=\"guardar\">Guardar</button></form>"}]}
```

Clon de `maintenance_green.json` con `test_perfil` + locator `#guardar` (el bueno). Comparte `project=checkout-suite` + `test_name=test_perfil` con `fresh_push.json` (que falla con `#guardar-cambios`), lo que hace que el triage detecte `has_green_baseline=true` + `dom_changed=true` → R3 maintenance.

### 2. `src/demo/seed.py` (modificado)

Línea 85: añadido `"perfil_green.json"` al final de la tupla de Org A:

```python
for name in ("maintenance_green.json", "maintenance_red.json", "flaky.json", "real.json", "perfil_green.json"):
```

Va tras `real.json` como baseline independiente; su "red" correspondiente es `fresh_push.json` que se ingiere en vivo durante el demo.

### 3. `tests/test_demo_seed.py` (modificado)

Añadidos:
- Helper `_categories_for_run(run_id)`: query `triage_verdicts` filtrada por `run_id` (distinto de `_verdict_categories` que filtra por `org_id`).
- Test `test_fresh_push_is_maintenance_with_baseline`: siembra Org A con seed (incluyendo `perfil_green`), ingiere `fresh_push.json` en Org A, triaje, y verifica `"maintenance" in cats`.

---

## Pytest Results

### Unit tests (non-integration)
```
498 passed, 89 deselected in 5.96s
```
El cambio en seed.py no rompió ningún test unitario.

### Integration tests (`tests/test_demo_seed.py -m integration`)
```
3 passed in 93.25s (0:01:33)
```
Los tres tests pasaron contra la BD prod (DATABASE_URL accesible):
- `test_seed_creates_two_orgs_with_processed_runs`
- `test_seed_is_idempotent`
- `test_fresh_push_is_maintenance_with_baseline` (nuevo)

El nuevo test confirmó que el triage de `fresh_push.json` sobre Org A (con `perfil_green` en baseline) devuelve categoría `maintenance`.

---

## Self-Review

- El fixture usa el mismo `project` y `test_name` que `fresh_push.json` — condición necesaria para `has_green_baseline`.
- El DOM del baseline (`#guardar`) difiere del DOM del push (`#guardar-cambios`) — condición para `dom_changed`.
- El orden en el seed (baseline antes del live-push) es correcto; el run de `perfil_green` es ingerido + triado en el seed, estableciendo el baseline antes de que llegue `fresh_push`.
- La limpieza del fixture `demo_user` borra por CASCADE (orgs → runs → verdicts → etc.), así que no hay contaminación entre tests.

## Concerns

Ninguno. Todos los tests pasan, el flujo de auto-clasificación `maintenance` está verificado en prod.

---

## Final-review fix — I1/I2

### I2 — `is_test_path` component match (not substring)

**File:** `src/ci/github_app.py`

Changed `_TEST_DIRS` from a tuple of `"tests/"` (with trailing slash) strings to a `frozenset` of bare names (`"tests"`, `"test"`, `"e2e"`, …). The directory check now splits the path on `/` and does a set-intersection: `set(p.split("/")) & _TEST_DIRS`, replacing the old `any(d in p for d in _TEST_DIRS)` substring scan. This means `notests/foo.ts` → `{"notests", "foo.ts"}` which has no intersection with `_TEST_DIRS`, so it returns `False`. The extension fast-path (`.spec.ts` etc.) is unchanged.

### I1 — `list_tree` warns on GitHub `truncated` flag

**Files:** `src/ci/github_app.py`, `src/repo_ingest/service.py`

- **`list_tree`** (github_app.py): after a successful response, reads `data.get("truncated")`, stores it as `self._last_tree_truncated: bool`, and emits `_log.warning("repo tree truncated for %s — partial index", self._repo)` when true. Returns the (partial) blob list as before — contract `-> list[str]` unchanged.
- **`index_repo_tests`** (service.py): after calling `codehost.list_tree()`, checks `getattr(codehost, "_last_tree_truncated", False)` and includes `"truncated": bool` in the returned dict. This avoids changing `list_tree`'s signature or adding a sibling method — the attribute is a lightweight out-band signal set as a side-effect of the call, pattern already used by the real codehost.

### Tests added

- `tests/test_github_app_list_tree.py`:
  - `test_is_test_path_rejects_non_test_paths` extended with `notests/foo.ts`, `nottest/util.ts`, `context/foo.ts` (all must return False).
  - `test_list_tree_truncated_logs_warning` — uses `caplog` to assert WARNING is emitted and blob paths are still returned.
  - `test_list_tree_not_truncated_no_warning` — verifies no spurious warning when `truncated:false`.
- `tests/test_repo_ingest_service.py`:
  - `test_truncated_codehost_sets_flag_in_result` — `TruncatedCodeHost` subclass sets `_last_tree_truncated=True`; asserts `result["truncated"] is True` and normal indexing still runs.
  - `test_empty_tree_returns_zero_counts` updated to expect `{"indexed": 0, "by_domain": {}, "skipped": 0, "truncated": False}`.

### Gate result

`DATABASE_URL= python3 -m pytest -m "not integration" -q` → **784 passed, rc=0**, `.env` restored (1167 bytes).

### Concerns

None. The `_last_tree_truncated` attribute approach is pragmatic: it avoids touching the public `list_tree` signature (used in multiple places) while giving `index_repo_tests` a clean way to detect and surface partial trees.
