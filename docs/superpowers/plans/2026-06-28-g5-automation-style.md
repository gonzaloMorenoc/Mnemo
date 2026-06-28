# QA Continuity AI · G5 (Automation al estilo del repo) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El Automation Agent genera tests usando los tests reales del repo (`test_assets`, G1) como few-shot, y se puede generar el test que falta directamente desde un gap `regla_sin_test` (G2).

**Architecture:** T1 recupera ejemplos de estilo de `test_assets` (backend puro). T2 los inyecta en `/v2/automation/generate` (cascada manual→auto→estándar; `org_id` nuevo). T3 cliente. T4 test-plan pasa `org_id`. T5 botón "Generar test" en el panel de gaps.

**Tech Stack:** Python/FastAPI/pytest · pgvector · Next.js/TS/vitest.

## Global Constraints

- **Agente PURO:** `generate_playwright_test(*, case, style_sample=None, provider=None)` NO cambia; el few-shot entra por `style_sample` (texto). El cruce/recuperación vive fuera.
- **Cascada del estilo:** `req.style_sample` (manual) → si no, `retrieve_style_examples(...)` (tests reales) → si no hay, `None` (el agente usa convenciones estándar).
- **`generate` requiere `org_id` + es membership-gated** vía `search_semantic` (no-miembro → `[]` → `None` → estándar; sin fuga). El retrieval nunca lanza (envuelto en try/except → `None`).
- **IA propone:** draft PR (`open_pr_with_new_file`), nunca auto-merge. Degrada (sin tests → estándar; sin LLM → plantilla `_fallback`).
- **Sin migración / tabla / endpoint nuevos** (reusa `test_assets`/`qa_knowledge`/`automation`/`GET /v2/knowledge/{id}`).
- **Verificación local = CI por tarea:** frontend `npm run lint:ci`+`test`+`tsc --noEmit`+`build`; backend pytest **sin `.env`** (`mv .env .env.bak; DATABASE_URL= python3 -m pytest -m "not integration" -q; mv .env.bak .env`). Si node_modules se corrompe (iCloud) → `npm --prefix frontend ci`. **No git worktree.** Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: `retrieve_style_examples` (backend, recuperación del few-shot)

**Files:** Create `src/automation/style.py`; Test `tests/test_automation_style.py`.

**Interfaces:** Consumes — `TestAssetRepository.search_semantic(*, user_id, org_id, query_embedding, k) -> List[Dict]` (cada row tiene `path`, `content`); `embedder.embed(text) -> Sequence[float]`. Produces — `retrieve_style_examples(*, user_id, org_id, case_text, asset_repo, embedder, k=3) -> str | None`.

- [ ] **Step 1: Write failing tests** (`tests/test_automation_style.py`): un `asset_repo` fake cuyo `search_semantic` devuelve 2 rows (`{"path":"e2e/login.spec.ts","content":"import {test} from '@playwright/test'..."}`, otro) y un `embedder` fake (`embed` → `[0.0]*384`): `retrieve_style_examples(...)` concatena ambos con `// --- ejemplo: <path> ---` y un `\n\n` entre bloques; con `search_semantic` → `[]` devuelve `None`; con un row de `content` vacío lo omite; respeta la cota (un `content` de 9000 chars → solo 1 bloque, recortado por la cota).

- [ ] **Step 2: Run, expect FAIL.** `python3 -m pytest tests/test_automation_style.py -q`

- [ ] **Step 3: Implement** `src/automation/style.py`:
```python
from typing import Optional

_MAX_EXAMPLES_CHARS = 6000


def retrieve_style_examples(*, user_id: str, org_id: str, case_text: str,
                            asset_repo, embedder, k: int = 3) -> Optional[str]:
    """Recupera los k test_assets más similares al caso y los concatena como
    ejemplos de estilo (few-shot). Devuelve None si no hay tests indexados.
    Membership-gated vía asset_repo.search_semantic (no-miembro → [] → None)."""
    embedding = list(embedder.embed(case_text or ""))
    rows = asset_repo.search_semantic(
        user_id=user_id, org_id=org_id, query_embedding=embedding, k=k)
    parts = []
    total = 0
    for r in rows or []:
        content = (r.get("content") or "").strip()
        if not content:
            continue
        block = f"// --- ejemplo: {r.get('path') or 'test'} ---\n{content}"
        if total + len(block) > _MAX_EXAMPLES_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else None
```

- [ ] **Step 4: Run PASS** + backend-no-`.env` gate green (`rc=0`, `.env` restaurado).
- [ ] **Step 5: Commit** `feat(automation): retrieve_style_examples (few-shot de test_assets)` + trailer.

---

## Task 2: `/v2/automation/generate` con `org_id` + cascada del estilo

**Files:** Modify `src/multitenant_models.py` (`AutomationGenerateRequest`), `src/api_v2.py` (`automation_generate`); Test `tests/test_api_v2_automation.py` (extender el existente).

**Interfaces:** Consumes — `retrieve_style_examples` (Task 1); `generate_playwright_test(*, case, style_sample)`, `_case_text(case)` (de `src/automation/agent.py`); `TestAssetRepository()` (tiene `.embedder`). Produces — `AutomationGenerateRequest{case: dict, org_id: str, style_sample: Optional[str]}`.

- [ ] **Step 1: Write failing tests** (extender `tests/test_api_v2_automation.py`): POST `/v2/automation/generate` con `{org_id, case}` y SIN `style_sample` → llama `retrieve_style_examples` (mockéalo para devolver `"EJEMPLOS"`) y pasa ese texto como `style_sample` a `generate_playwright_test` (mockéalo y captura el kwarg); con `style_sample` manual → NO llama `retrieve_style_examples` (lo usa tal cual); cuando `retrieve_style_examples` devuelve `None` → `style_sample=None` (estándar); `case` vacío → 400; sin auth → 401.

- [ ] **Step 2: Run, expect FAIL.** `python3 -m pytest tests/test_api_v2_automation.py -q`

- [ ] **Step 3a: Implement** el modelo (`src/multitenant_models.py`):
```python
class AutomationGenerateRequest(BaseModel):
    case: dict
    org_id: str
    style_sample: Optional[str] = None
```

- [ ] **Step 3b: Implement** el endpoint (`src/api_v2.py`, reemplaza `automation_generate`). Añade el import `from src.automation.style import retrieve_style_examples`, `from src.automation.agent import generate_playwright_test, _case_text` (ajusta a los imports existentes), `from src.repo_ingest.repository import TestAssetRepository`:
```python
@router.post("/automation/generate", response_model=Dict[str, Any])
def automation_generate(
    req: AutomationGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """Genera un test Playwright (.spec.ts) a partir de un caso.

    El estilo sigue una cascada: style_sample manual → tests reales del repo
    (test_assets, few-shot) → convenciones estándar. El retrieval del few-shot
    es membership-gated (search_semantic); un no-miembro no obtiene ejemplos.
    """
    if not req.case:
        raise HTTPException(status_code=400, detail="case requerido")
    examples = req.style_sample
    if not examples:
        try:
            repo = TestAssetRepository()
            examples = retrieve_style_examples(
                user_id=user.user_id, org_id=req.org_id,
                case_text=_case_text(req.case),
                asset_repo=repo, embedder=repo.embedder)
        except Exception:
            examples = None
    return generate_playwright_test(case=req.case, style_sample=examples)
```

- [ ] **Step 4: Run PASS** + backend-no-`.env` gate green.
- [ ] **Step 5: Commit** `feat(automation): generate usa el few-shot del repo (org_id + cascada)` + trailer.

---

## Task 3: cliente — `org_id` en `generatePlaywrightTest` + `getKnowledgeItem`

**Files:** Modify `frontend/src/lib/api/endpoints.ts`; Test `frontend/src/lib/api/__tests__/automation.test.ts` (o el que cubra estos clientes; crea uno si no existe).

**Interfaces:** Consumes — `apiRequest`, tipos `TestCase`, `GeneratedTest`, `KnowledgeItem`. Produces — `generatePlaywrightTest(token, {case, org_id, style_sample?})`; `getKnowledgeItem(token, {org_id, id}) -> KnowledgeItem`.

- [ ] **Step 1: Write failing tests** (vitest, `global.fetch` spy): `generatePlaywrightTest(token, {case, org_id:"o1"})` POSTs `/api/v2/automation/generate` con `org_id` en el body; `getKnowledgeItem(token, {org_id:"o1", id:"k1"})` GETs `/api/v2/knowledge/k1?org_id=o1` y parsea el `KnowledgeItem`.

- [ ] **Step 2: Run, expect FAIL.** `npm --prefix frontend test -- automation`

- [ ] **Step 3: Implement** (`frontend/src/lib/api/endpoints.ts`): cambia la firma de `generatePlaywrightTest` para incluir `org_id`, y añade `getKnowledgeItem`:
```ts
export function generatePlaywrightTest(
  token: string,
  body: { case: TestCase; org_id: string; style_sample?: string },
) {
  return apiRequest<GeneratedTest>("/api/v2/automation/generate", "POST", { token, body });
}

export function getKnowledgeItem(token: string, params: { org_id: string; id: string }) {
  return apiRequest<KnowledgeItem>(
    `/api/v2/knowledge/${encodeURIComponent(params.id)}?org_id=${encodeURIComponent(params.org_id)}`,
    "GET", { token },
  );
}
```

- [ ] **Step 4: Run** `npm run lint:ci` + `npm test` + `npx tsc --noEmit` (verde). **Nota:** `tsc` marcará el caller de `generatePlaywrightTest` en test-plan (le falta `org_id`) — eso se arregla en Task 4; si el build falla solo por eso, continúa a Task 4 y verifica el build allí. Mantén `lint:ci`+`test` verdes aquí.
- [ ] **Step 5: Commit** `feat(frontend): org_id en generatePlaywrightTest + getKnowledgeItem` + trailer.

---

## Task 4: test-plan pasa `org_id` al generar

**Files:** Modify `frontend/src/app/app/test-plan/page.tsx` (`CasePlaywrightSection`); Test el de la página.

- [ ] **Step 1: Read** `CasePlaywrightSection` — ya recibe `activeOrgId` y llama `generatePlaywrightTest(accessToken, { case: ..., ...(styleSample.trim()?{style_sample}:{}) })`. Falta `org_id`.
- [ ] **Step 2: Write/adjust test** (vitest): al pulsar "Generar test Playwright", `generatePlaywrightTest` se llama con `org_id: activeOrgId` en el body (mockéalo y captura el argumento). Mantén el caso con `style_sample` cuando el textarea tiene contenido.
- [ ] **Step 3: Implement** — añade `org_id: activeOrgId` al body de la llamada `generatePlaywrightTest` dentro de `CasePlaywrightSection`:
```ts
generatePlaywrightTest(accessToken, {
  case: { title: tc.title, gherkin: tc.gherkin, steps: tc.steps },  // mantener la forma actual del case
  org_id: activeOrgId,
  ...(styleSample.trim() ? { style_sample: styleSample.trim() } : {}),
})
```
(Conserva exactamente la forma del `case` que ya construye el componente; solo añade `org_id`.)
- [ ] **Step 4: Run** `npm run lint:ci` + `npm test` + `npx tsc --noEmit` + `npm run build` (todo verde; el caller queda completo).
- [ ] **Step 5: Commit** `feat(frontend): test-plan pasa org_id al generar (few-shot del repo)` + trailer.

---

## Task 5: "Generar test" desde un gap `regla_sin_test` en `/app/graph`

**Files:** Modify `frontend/src/app/app/graph/page.tsx`; Test el de la página de graph.

**Interfaces:** Consumes — `getKnowledgeItem`, `generatePlaywrightTest`, `openAutomationPr` (clientes); el gap tiene `{kind:"regla_sin_test", title, affected: string[]}` (`affected[0]` = id de `qa_knowledge`); `useActiveOrg`, `useAuth`, `toast`.

- [ ] **Step 1: Write failing test** (vitest, en el test de la página de graph): renderiza el panel con un gap `{kind:"regla_sin_test", severity:"alta", title:"Regla X", recommendation:"...", affected:["k1"]}`; mockea `getKnowledgeItem` → `{id:"k1", title:"Regla X", challenge:"c", approach:"a", outcome:"o"}` y `generatePlaywrightTest` → `{code:"CODE", filename:"regla-x.spec.ts", notes:""}`. Al pulsar "Generar test" en ese gap: se llama `getKnowledgeItem({org_id, id:"k1"})` y luego `generatePlaywrightTest` con un `case` `{title:"Regla X", steps:["c","a","o"]}` y `org_id`; el código `CODE` aparece en un `<pre>`. (Gaps de otro `kind` no muestran el botón.)

- [ ] **Step 2: Run, expect FAIL.** `npm --prefix frontend test -- graph`

- [ ] **Step 3: Implement** — añade un sub-componente `GapTestSection` (en el mismo fichero, espejo de `CasePlaywrightSection`) y renderízalo solo cuando `gap.kind === "regla_sin_test" && gap.affected.length > 0`:
```tsx
function GapTestSection({ gap, accessToken, activeOrgId }: {
  gap: CoverageGap; accessToken: string; activeOrgId: string;
}) {
  const [result, setResult] = useState<GeneratedTest | null>(null);
  const genMut = useMutation({
    mutationFn: async () => {
      const item = await getKnowledgeItem(accessToken, { org_id: activeOrgId, id: gap.affected[0] });
      const steps = [item.challenge, item.approach, item.outcome].filter(Boolean) as string[];
      return generatePlaywrightTest(accessToken, {
        case: { title: item.title, steps },
        org_id: activeOrgId,
      });
    },
    onSuccess: (r) => setResult(r),
    onError: () => toast.error("No se pudo generar el test"),
  });
  const prMut = useMutation({
    mutationFn: () => openAutomationPr(accessToken, {
      org_id: activeOrgId, code: result!.code, filename: result!.filename,
    }),
    onSuccess: (r) => toast.success(`PR abierto: ${r.pr_url}`),
    onError: () => toast.error("No se pudo abrir el PR"),
  });
  return (
    <div className="mt-2">
      <Button size="sm" variant="outline" disabled={genMut.isPending}
        onClick={() => genMut.mutate()} data-testid={`gap-generate-${gap.affected[0]}`}>
        {genMut.isPending ? "Generando…" : "Generar test"}
      </Button>
      {result && (
        <div className="mt-2">
          <pre className="rounded bg-zinc-900 text-zinc-100 p-3 text-xs overflow-x-auto whitespace-pre-wrap">{result.code}</pre>
          <Button size="sm" className="mt-2" disabled={prMut.isPending} onClick={() => prMut.mutate()}>
            {prMut.isPending ? "Abriendo PR…" : "Abrir draft PR"}
          </Button>
        </div>
      )}
    </div>
  );
}
```
Importa lo necesario (`useMutation`, `getKnowledgeItem`, `generatePlaywrightTest`, `openAutomationPr`, `GeneratedTest`, `Button`, `useState`). En la card del gap, tras la recomendación: `{gap.kind === "regla_sin_test" && gap.affected.length > 0 && <GapTestSection gap={gap} accessToken={accessToken} activeOrgId={activeOrgId} />}` (usa el token/org que ya tenga la página; si no, vía `useAuth`/`useActiveOrg`).

- [ ] **Step 4: Run** `npm run lint:ci` + `npm test` + `npx tsc --noEmit` + `npm run build` (todo verde).
- [ ] **Step 5: Commit** `feat(graph): generar el test que falta desde un gap regla_sin_test` + trailer.

---

## Notas de cierre
- **Orden:** T1 → T2 (backend) → T3 (cliente) → T4 (test-plan) → T5 (graph). T3 deja un caller incompleto en test-plan que T4 cierra (anotado en T3 Step 4).
- **Reusa:** `generate_playwright_test`/`open_pr_with_new_file` (#46), `TestAssetRepository.search_semantic`+`.embedder` (G1), el gap `regla_sin_test` (G2), `GET /v2/knowledge/{id}` (1a), el patrón de UI de `CasePlaywrightSection`.
- **Determinista + degrada:** el retrieval nunca lanza (try/except → None); sin tests → estándar; sin LLM → `_fallback`; sin GitHub → 503 en el PR.
- **Sin migración / endpoint / tabla.** Verificación local=CI por tarea (recordar `npm --prefix frontend ci` si node_modules se corrompe).
- **Fuera de alcance:** API/contract/SQL tests; ejecutar/compilar el test; reranking por framework; persistir el test generado.
