# Bloque C · C2 — UI de la demo (briefing + ROI) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El run view abre con un resumen ejecutivo (briefing de B5) y muestra el ROI honesto — lo que ve primero un comprador en la demo.

**Architecture:** T1 añade `getBriefing` al cliente + el tipo. T2 crea `BriefingCard` y la monta arriba del run view. T3 crea `RoiPanel` (cálculo en frontend con supuesto visible) y lo monta.

**Tech Stack:** Next.js/TS, @tanstack/react-query, shadcn/ui, vitest + @testing-library. **Tests: `npm test` (vitest) en `frontend/` — NO pytest.** Trabaja siempre dentro de `frontend/`.

## Global Constraints

- **Solo frontend:** el endpoint `GET /v2/runs/{id}/briefing` ya existe (B5). No tocar el backend.
- **ROI honesto:** supuesto `MIN_POR_FALLO = 15` mostrado EN PANTALLA; coste `0 €/release` como etiqueta de diseño (Ollama local), no como número medido.
- **Degradable:** si `getBriefing` falla, la `BriefingCard` muestra un fallback discreto y el resto del run view sigue.
- **Patrón existente:** componentes `"use client"` con `useQuery({queryFn: () => getX(accessToken!, runId), enabled: Boolean(accessToken && runId), retry: false})`, `Card`/`Badge` de shadcn, `useAuth()` para el token — igual que `CertificateCard`.
- Commits `feat:`/`test:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Cliente `getBriefing` + tipo `BriefingResponse`

**Files:** Modify `frontend/src/lib/api/endpoints.ts`, `frontend/src/lib/api/types.ts`; Test `frontend/src/lib/api/__tests__/getBriefing.test.ts` (o el archivo de tests del cliente si existe — busca el patrón).

**Interfaces:** Produces — `getBriefing(token: string, runId: string): Promise<BriefingResponse>`; `BriefingResponse`.

- [ ] **Step 1: Add the type** to `frontend/src/lib/api/types.ts`:

```ts
export interface BriefingResponse {
  verdict: string;
  summary: string;
  recommendation: string;
  highlights: string[];
  citations: string[];
}
```

- [ ] **Step 2: Add the endpoint** to `frontend/src/lib/api/endpoints.ts` (mirror `getAssuranceVerdict`; add `BriefingResponse` to the type import block):

```ts
export function getBriefing(token: string, runId: string) {
  return apiRequest<BriefingResponse>(
    `/api/v2/runs/${encodeURIComponent(runId)}/briefing`,
    "GET",
    { token },
  );
}
```

- [ ] **Step 3: Write the test** — find how the existing client/endpoints are tested (look in `frontend/src/lib/api/__tests__` or `frontend/src/test`; if `apiRequest` is mocked elsewhere, mirror that). A minimal test that mocks `apiRequest` and asserts `getBriefing` calls the right path:

```ts
import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/api/client", () => ({ apiRequest: vi.fn().mockResolvedValue({
  verdict: "apto", summary: "s", recommendation: "r", highlights: [], citations: [] }) }));

import { apiRequest } from "@/lib/api/client";
import { getBriefing } from "@/lib/api/endpoints";

describe("getBriefing", () => {
  it("calls the briefing endpoint for the run", async () => {
    const res = await getBriefing("tok", "r1");
    expect(apiRequest).toHaveBeenCalledWith("/api/v2/runs/r1/briefing", "GET", { token: "tok" });
    expect(res.verdict).toBe("apto");
  });
});
```

- [ ] **Step 4: Run** — from `frontend/`: `npm test -- getBriefing` (or the project's vitest invocation). Verify it passes (and the full `npm test` stays green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/endpoints.ts frontend/src/lib/api/types.ts frontend/src/lib/api/__tests__/
git commit -m "feat(ui): cliente getBriefing + tipo BriefingResponse (endpoint de B5)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `BriefingCard` + montaje arriba del run view

**Files:** Create `frontend/src/components/autopilot/BriefingCard.tsx`, `frontend/src/components/autopilot/__tests__/BriefingCard.test.tsx`; Modify `frontend/src/app/app/autopilot/page.tsx`.

**Interfaces:** Consumes — `getBriefing` (T1). Produces — `BriefingCard({ runId }: { runId: string })`.

- [ ] **Step 1: Write the failing test** — `frontend/src/components/autopilot/__tests__/BriefingCard.test.tsx` (mirror `ActionsPanel.test.tsx`: jsdom, mock auth + endpoints, `renderWithClient`):

```tsx
// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({ getBriefing: vi.fn() }));

import { getBriefing } from "@/lib/api/endpoints";
import { BriefingCard } from "@/components/autopilot/BriefingCard";

afterEach(() => vi.clearAllMocks());
function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("BriefingCard", () => {
  it("muestra el resumen ejecutivo del run", async () => {
    (getBriefing as ReturnType<typeof vi.fn>).mockResolvedValue({
      verdict: "apto-con-reservas", summary: "Checkout falla por un 500.",
      recommendation: "Revisar el parche propuesto.", highlights: ["1 defecto real"], citations: ["family:f1"] });
    renderWithClient(<BriefingCard runId="r1" />);
    expect(await screen.findByText("Checkout falla por un 500.")).toBeInTheDocument();
    expect(screen.getByText("apto-con-reservas")).toBeInTheDocument();
    expect(screen.getByText("Revisar el parche propuesto.")).toBeInTheDocument();
  });

  it("muestra un fallback discreto si el briefing falla (no rompe)", async () => {
    (getBriefing as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("llm down"));
    renderWithClient(<BriefingCard runId="r1" />);
    expect(await screen.findByText(/resumen no disponible/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect FAIL** (no `BriefingCard`).

- [ ] **Step 3: Create `BriefingCard.tsx`** (mirror `CertificateCard`):

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getBriefing } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function BriefingCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["briefing", runId],
    queryFn: () => getBriefing(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
    retry: false,
  });
  const b = query.data;
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700">Resumen ejecutivo</h2>
        {b && <Badge>{b.verdict}</Badge>}
      </div>
      {b ? (
        <div className="space-y-2 text-sm text-zinc-600">
          <p className="text-zinc-800">{b.summary}</p>
          <p><strong className="text-zinc-900">Recomendación:</strong> {b.recommendation}</p>
          {b.highlights.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5">
              {b.highlights.map((h, i) => <li key={i}>{h}</li>)}
            </ul>
          )}
        </div>
      ) : (
        <p className="text-sm text-zinc-500">
          {query.isError ? "Resumen no disponible." : "Cargando resumen…"}
        </p>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: Mount it** in `frontend/src/app/app/autopilot/page.tsx` — import `BriefingCard` and render it FIRST inside the `{runId && (...)}` block, before `<TriageVerdictList runId={runId} />`:

```tsx
          <BriefingCard runId={runId} />
          <TriageVerdictList runId={runId} />
```

- [ ] **Step 5: Run, expect PASS** — `npm test -- BriefingCard` → PASS; full `npm test` → green. (If there's a typecheck/lint script, run it too.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/autopilot/BriefingCard.tsx frontend/src/components/autopilot/__tests__/BriefingCard.test.tsx frontend/src/app/app/autopilot/page.tsx
git commit -m "feat(ui): BriefingCard — resumen ejecutivo (B5) arriba del run view, degradable

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: `RoiPanel` (ROI honesto) + montaje

**Files:** Create `frontend/src/components/autopilot/RoiPanel.tsx`, `frontend/src/components/autopilot/__tests__/RoiPanel.test.tsx`; Modify `frontend/src/app/app/autopilot/page.tsx`.

**Interfaces:** Consumes — the triage-verdicts client function that `TriageVerdictList` already uses (find its exact name in `endpoints.ts`/`TriageVerdictList.tsx`; it returns `TriageVerdict[]` with `category` + `requires_approval`). Produces — `RoiPanel({ runId }: { runId: string })`.

- [ ] **Step 1: Find the triage-verdicts client function** — read `frontend/src/components/autopilot/TriageVerdictList.tsx` to see exactly how it loads the run's verdicts (the `getX` it calls, e.g. `getTriageVerdicts`/`getTriageRun`). The `RoiPanel` reuses that SAME function. Note its exact name + return type for the steps below (substitute it for `getTriageVerdicts` wherever it appears).

- [ ] **Step 2: Write the failing test** — `frontend/src/components/autopilot/__tests__/RoiPanel.test.tsx`:

```tsx
// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({ getTriageVerdicts: vi.fn() }));  // use the REAL name from Step 1

import { getTriageVerdicts } from "@/lib/api/endpoints";
import { RoiPanel } from "@/components/autopilot/RoiPanel";

afterEach(() => vi.clearAllMocks());
function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("RoiPanel", () => {
  it("calcula horas ahorradas de los auto-triados y muestra el supuesto + 0€", async () => {
    // 4 auto-triados (requires_approval false, category != unknown) + 1 que requiere approval + 1 unknown
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "1", category: "flaky", requires_approval: false },
      { id: "2", category: "maintenance", requires_approval: false },
      { id: "3", category: "real", requires_approval: false },
      { id: "4", category: "flaky", requires_approval: false },
      { id: "5", category: "real", requires_approval: true },
      { id: "6", category: "unknown", requires_approval: true },
    ]);
    renderWithClient(<RoiPanel runId="r1" />);
    expect(await screen.findByText(/1\.0\s*h/)).toBeInTheDocument();   // 4 × 15 / 60 = 1.0 h
    expect(screen.getByText(/15 min/)).toBeInTheDocument();            // el supuesto visible
    expect(screen.getByText(/0\s*€/)).toBeInTheDocument();            // coste 0€
  });

  it("no rompe con 0 veredictos", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderWithClient(<RoiPanel runId="r1" />);
    expect(await screen.findByText(/0\.0\s*h/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run, expect FAIL**.

- [ ] **Step 4: Create `RoiPanel.tsx`** (substitute the real triage-verdicts function name from Step 1):

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getTriageVerdicts } from "@/lib/api/endpoints";  // REAL name from Step 1
import { Card } from "@/components/ui/card";

const MIN_POR_FALLO = 15;

export function RoiPanel({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["triage", runId],
    queryFn: () => getTriageVerdicts(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
    retry: false,
  });
  const verdicts = query.data ?? [];
  const autoTriados = verdicts.filter((v) => !v.requires_approval && v.category !== "unknown").length;
  const horas = ((autoTriados * MIN_POR_FALLO) / 60).toFixed(1);
  return (
    <Card className="space-y-2 p-5">
      <h2 className="text-sm font-medium text-zinc-700">Retorno (ROI)</h2>
      <div className="flex gap-6 text-sm text-zinc-600">
        <span><strong className="text-zinc-900">{autoTriados}</strong> auto-triados</span>
        <span><strong className="text-zinc-900">{horas} h</strong> ahorradas</span>
        <span><strong className="text-zinc-900">0 €</strong> / release</span>
      </div>
      <p className="text-xs text-zinc-400">
        Supuesto: 15 min de triaje manual por fallo. Coste de API 0 € por ejecutar el modelo en local.
      </p>
    </Card>
  );
}
```

(If `TriageVerdict` from Step 1 doesn't have exactly `requires_approval`/`category`, adapt the filter to the real fields. If the verdicts endpoint returns an object wrapping the list, unwrap it.)

- [ ] **Step 5: Mount it** in `autopilot/page.tsx` — render `<RoiPanel runId={runId} />` after `<GateCard runId={runId} />` (or next to the certificate, a visible spot).

- [ ] **Step 6: Run, expect PASS** — `npm test -- RoiPanel` → PASS; full `npm test` → green.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/autopilot/RoiPanel.tsx frontend/src/components/autopilot/__tests__/RoiPanel.test.tsx frontend/src/app/app/autopilot/page.tsx
git commit -m "feat(ui): RoiPanel — horas ahorradas (supuesto visible) + coste 0€/release

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **El ROI reusa los veredictos de triaje** que el run view ya carga (mismo `queryKey` que `TriageVerdictList` → react-query los comparte/cachea, sin doble fetch).
- **Honestidad:** el supuesto (15 min/fallo) y el "0 € por modelo en local" están a la vista — no se vende un número de API medido.
- **Degradación:** `retry:false` + el fallback de `BriefingCard` evitan que un briefing caído rompa la página.
- **Fuera de alcance:** C3 (PDF del certificado), C4 (guion 3 actos + push en vivo + aislamiento A/B + ensayo); Bloque D.
