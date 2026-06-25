# F5b-2 — Frontend del foso (métricas + etiquetado) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el lazo de aprendizaje en la UI: una página `/app/calibration` que muestra la precisión del motor por cliente, y un control en `/app/defects` para etiquetar familias (→ calibra el motor).

**Architecture:** Frontend Next.js 16. Replica el patrón de F5b-1: route handlers proxy → `apiRequest` → funciones en `endpoints.ts` → componentes con TanStack Query. Página nueva de métricas; un componente `FamilyLabelControl` integrado en la página de defects existente.

**Tech Stack:** TypeScript, Next.js 16 App Router, Tailwind v4, TanStack Query v5, Vitest + Testing Library. Todo bajo `frontend/`.

## Global Constraints

- **Patrón API:** `apiRequest<T>(path, method, { token, body })`; route handlers `proxyToBackend(request, "/v2/...", { method, body?, contentType? })` (forwardea `Authorization`).
- **Contratos backend (de F5a #22, verbatim):** `CalibrationMetricsResponse {total: int, aciertos: int, accuracy: float, familias_calibradas: int, por_categoria: dict}`; `SetFamilyLabelRequest {label, reason?}`; `FamilyLabelResponse {family_id, label}`. `label ∈ {flaky, real, maintenance, infra, unknown}`.
- **`DefectLineageResponse.family` NO trae `label`** → `FamilyLabelControl` no pre-selecciona; el selector inicia en `"unknown"`.
- **Auth:** `useAuth()` → `accessToken`; queries `enabled: Boolean(accessToken && orgId/familyId)`; mutations pasan el token.
- **UI en español**, componentes `@/components/ui/*` (Card, Badge, Button, Input, Skeleton), estilo Tailwind `zinc` (como `defects/page.tsx`). Toasts con `sonner`.
- **Tests:** Vitest desde `frontend/` (`npm --prefix frontend test`); component tests llevan `// @vitest-environment jsdom` como primera línea (infra `test-setup.ts` ya existe). Mocks (sin red).
- **Apilado sobre #23**; consume calibración de #22 (no en `main` aún) — los tests usan mocks; e2e tras mergear #22+#23.
- Commits `feat:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `frontend/src/lib/api/types.ts` | modificar | `CalibrationMetrics`, `FamilyLabel` |
| `frontend/src/lib/api/endpoints.ts` | modificar | `getCalibrationMetrics`, `setFamilyLabel` |
| `frontend/src/app/api/v2/calibration/metrics/route.ts` | crear | proxy GET métricas |
| `frontend/src/app/api/v2/defects/[family_id]/label/route.ts` | crear | proxy PATCH label |
| `frontend/src/lib/api/__tests__/foso-endpoints.test.ts` | crear | tests de endpoints |
| `frontend/src/app/app/calibration/page.tsx` | crear | página del foso (métricas) |
| `frontend/src/app/app/calibration/__tests__/CalibrationPage.test.tsx` | crear | test de la página |
| `frontend/src/components/layout/sidebar-nav.tsx` | modificar | ítem "Calibración" |
| `frontend/src/components/autopilot/FamilyLabelControl.tsx` | crear | etiquetar familia |
| `frontend/src/components/autopilot/__tests__/FamilyLabelControl.test.tsx` | crear | test del control |
| `frontend/src/app/app/defects/page.tsx` | modificar | montar `FamilyLabelControl` |

---

## Task 1: API layer (tipos + endpoints + route handlers)

**Files:** Modify `src/lib/api/types.ts`, `src/lib/api/endpoints.ts`; create the two route handlers; create `src/lib/api/__tests__/foso-endpoints.test.ts`. (All under `frontend/`.)

**Interfaces:**
- Produces: `CalibrationMetrics`, `FamilyLabel` types; `getCalibrationMetrics(token, orgId)`, `setFamilyLabel(token, familyId, label, reason?)`.

- [ ] **Step 1: Types** — append to `frontend/src/lib/api/types.ts`:

```typescript
export interface CalibrationMetrics {
  total: number;
  aciertos: number;
  accuracy: number;
  familias_calibradas: number;
  por_categoria: Record<string, number>;
}

export interface FamilyLabel {
  family_id: string;
  label: string;
}
```

- [ ] **Step 2: Write the failing endpoint tests** — `frontend/src/lib/api/__tests__/foso-endpoints.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";

import { getCalibrationMetrics, setFamilyLabel } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok, status, text: async () => JSON.stringify(json),
  } as unknown as Response);
}

function lastCall(spy: ReturnType<typeof mockFetch>) {
  const [url, init] = spy.mock.calls[0];
  return { url: String(url), init: init as RequestInit };
}

describe("foso endpoints", () => {
  it("getCalibrationMetrics → GET /api/v2/calibration/metrics?org_id= con bearer", async () => {
    const spy = mockFetch({ total: 3, aciertos: 2, accuracy: 0.6667, familias_calibradas: 2, por_categoria: { flaky: 2, real: 1 } });
    const out = await getCalibrationMetrics("tok", "org-1");
    expect(out.familias_calibradas).toBe(2);
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/calibration/metrics?org_id=org-1");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("setFamilyLabel → PATCH /api/v2/defects/{id}/label con body {label, reason}", async () => {
    const spy = mockFetch({ family_id: "fam-1", label: "flaky" });
    const out = await setFamilyLabel("tok", "fam-1", "flaky", "histórico flaky");
    expect(out.label).toBe("flaky");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/defects/fam-1/label");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ label: "flaky", reason: "histórico flaky" });
  });

  it("setFamilyLabel envía reason vacío por defecto", async () => {
    const spy = mockFetch({ family_id: "fam-1", label: "real" });
    await setFamilyLabel("tok", "fam-1", "real");
    expect(JSON.parse(lastCall(spy).init.body as string)).toEqual({ label: "real", reason: "" });
  });
});
```

- [ ] **Step 3: Run, expect FAIL**

Run (from repo root): `npm --prefix frontend test -- --run foso-endpoints` → FAIL (functions not exported).

- [ ] **Step 4: Endpoint functions** — append to `frontend/src/lib/api/endpoints.ts` (add `CalibrationMetrics, FamilyLabel` to the `import type {...}` block):

```typescript
export function getCalibrationMetrics(token: string, orgId: string) {
  return apiRequest<CalibrationMetrics>(
    `/api/v2/calibration/metrics?org_id=${encodeURIComponent(orgId)}`, "GET", { token });
}

export function setFamilyLabel(token: string, familyId: string, label: string, reason = "") {
  return apiRequest<FamilyLabel>(
    `/api/v2/defects/${encodeURIComponent(familyId)}/label`, "PATCH", { token, body: { label, reason } });
}
```

- [ ] **Step 5: Route handlers** — create both (Next 16: `params` is a Promise):

`frontend/src/app/api/v2/calibration/metrics/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, `/v2/calibration/metrics${request.nextUrl.search}`, { method: "GET" });
}
```

`frontend/src/app/api/v2/defects/[family_id]/label/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ family_id: string }> }) {
  const { family_id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/defects/${encodeURIComponent(family_id)}/label`,
    { method: "PATCH", body, contentType: "application/json" });
}
```

- [ ] **Step 6: Run, expect PASS**

Run: `npm --prefix frontend test -- --run foso-endpoints` → PASS (3 tests). Then `npm --prefix frontend exec tsc -- --noEmit` → clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api/types.ts frontend/src/lib/api/endpoints.ts frontend/src/app/api/v2/calibration frontend/src/app/api/v2/defects/[family_id]/label frontend/src/lib/api/__tests__/foso-endpoints.test.ts
git commit -m "feat(ui): API layer del foso (getCalibrationMetrics + setFamilyLabel + proxies)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: Página del foso (`/app/calibration`) + nav

**Files:** Create `src/app/app/calibration/page.tsx`, `src/app/app/calibration/__tests__/CalibrationPage.test.tsx`; modify `src/components/layout/sidebar-nav.tsx`.

**Interfaces:**
- Consumes: `getCalibrationMetrics`, `getOrganizations` (Task 1 + existing).

- [ ] **Step 1: Nav item** — in `src/components/layout/sidebar-nav.tsx`, add `Gauge` to the `lucide-react` import and this entry to `navItems` (after the Autopilot line):

```typescript
  { href: "/app/calibration", label: "Calibración", icon: Gauge },
```

- [ ] **Step 2: Write the failing test** — `src/app/app/calibration/__tests__/CalibrationPage.test.tsx`:

```tsx
// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({
  getCalibrationMetrics: vi.fn(),
  getOrganizations: vi.fn().mockResolvedValue([{ id: "org-1", name: "Org" }]),
}));

import { getCalibrationMetrics } from "@/lib/api/endpoints";
import CalibrationPage from "@/app/app/calibration/page";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CalibrationPage", () => {
  it("muestra la precisión y el desglose", async () => {
    (getCalibrationMetrics as ReturnType<typeof vi.fn>).mockResolvedValue({
      total: 3, aciertos: 2, accuracy: 0.6667, familias_calibradas: 2, por_categoria: { flaky: 2, real: 1 } });
    renderWithClient(<CalibrationPage />);
    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/2 familias calibradas/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run, expect FAIL**

Run: `npm --prefix frontend test -- --run CalibrationPage` → FAIL (page missing).

- [ ] **Step 4: Implement the page** — `src/app/app/calibration/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getCalibrationMetrics, getOrganizations } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function CalibrationPage() {
  const { accessToken } = useAuth();
  const [orgId, setOrgId] = useState("");

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const activeOrg = orgId || orgsQuery.data?.[0]?.id || "";

  const metricsQuery = useQuery({
    queryKey: ["calibration", activeOrg],
    queryFn: () => getCalibrationMetrics(accessToken!, activeOrg),
    enabled: Boolean(accessToken && activeOrg),
  });

  const m = metricsQuery.data;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Calibración</h1>
        <p className="text-sm text-zinc-500">Precisión del motor de triaje con tus correcciones (el foso).</p>
      </div>

      {orgsQuery.data && orgsQuery.data.length > 1 && (
        <select
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          value={activeOrg}
          onChange={(e) => setOrgId(e.target.value)}
        >
          {orgsQuery.data.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      )}

      {metricsQuery.isLoading && <Skeleton className="h-40 w-full max-w-xl" />}
      {metricsQuery.isError && (
        <Card className="max-w-xl p-5"><p className="text-sm text-red-600">No se pudieron cargar las métricas.</p></Card>
      )}
      {m && m.total === 0 && (
        <Card className="max-w-xl p-5"><p className="text-sm text-zinc-500">
          Aún no hay correcciones. Etiqueta familias en Defect DNA para calibrar el motor.</p></Card>
      )}
      {m && m.total > 0 && (
        <Card className="max-w-xl space-y-4 p-6">
          <div>
            <p className="text-5xl font-semibold tracking-tight text-zinc-900">{(m.accuracy * 100).toFixed(0)}%</p>
            <p className="text-sm text-zinc-500">precisión del motor ({m.aciertos}/{m.total} correcciones coincidieron)</p>
          </div>
          <p className="text-sm text-zinc-600">{m.familias_calibradas} familias calibradas</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(m.por_categoria).map(([cat, n]) => (
              <Badge key={cat}>{cat}: {n}</Badge>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run, expect PASS**

Run: `npm --prefix frontend test -- --run CalibrationPage` → PASS. Then `npm --prefix frontend exec tsc -- --noEmit` → clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/app/calibration frontend/src/components/layout/sidebar-nav.tsx
git commit -m "feat(ui): página /app/calibration (métricas del foso) + nav

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Etiquetado (`FamilyLabelControl` en `/app/defects`)

**Files:** Create `src/components/autopilot/FamilyLabelControl.tsx`, `src/components/autopilot/__tests__/FamilyLabelControl.test.tsx`; modify `src/app/app/defects/page.tsx`.

**Interfaces:**
- Consumes: `setFamilyLabel` (Task 1).
- Produces: `FamilyLabelControl({ familyId: string })`.

- [ ] **Step 1: Write the failing test** — `src/components/autopilot/__tests__/FamilyLabelControl.test.tsx`:

```tsx
// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({ setFamilyLabel: vi.fn() }));

import { setFamilyLabel } from "@/lib/api/endpoints";
import { FamilyLabelControl } from "@/components/autopilot/FamilyLabelControl";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("FamilyLabelControl", () => {
  it("etiqueta la familia con la categoría elegida", async () => {
    (setFamilyLabel as ReturnType<typeof vi.fn>).mockResolvedValue({ family_id: "fam-1", label: "flaky" });
    renderWithClient(<FamilyLabelControl familyId="fam-1" />);
    fireEvent.change(screen.getByLabelText(/categoría/i), { target: { value: "flaky" } });
    fireEvent.click(screen.getByRole("button", { name: /etiquetar familia/i }));
    await waitFor(() => expect(setFamilyLabel).toHaveBeenCalledWith("tok", "fam-1", "flaky", ""));
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run: `npm --prefix frontend test -- --run FamilyLabelControl` → FAIL (component missing).

- [ ] **Step 3: Implement `FamilyLabelControl`** — `src/components/autopilot/FamilyLabelControl.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { setFamilyLabel } from "@/lib/api/endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const LABELS = ["unknown", "flaky", "real", "maintenance", "infra"];

export function FamilyLabelControl({ familyId }: { familyId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const [label, setLabel] = useState("unknown");
  const [reason, setReason] = useState("");

  const mut = useMutation({
    mutationFn: () => setFamilyLabel(accessToken!, familyId, label, reason),
    onSuccess: () => {
      toast.success("Familia etiquetada.");
      qc.invalidateQueries({ queryKey: ["lineage", familyId] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="mt-3 space-y-2 border-t border-zinc-100 pt-3">
      <p className="text-xs font-medium text-zinc-500">Calibrar (etiqueta esta familia)</p>
      <div className="space-y-1">
        <Label htmlFor="cat">Categoría</Label>
        <select
          id="cat"
          className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        >
          {LABELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
      <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="motivo (opcional)" />
      <Button className="text-xs" disabled={mut.isPending} onClick={() => mut.mutate()}>
        {mut.isPending ? "Guardando…" : "Etiquetar familia"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Mount it in `defects/page.tsx`** — add the import and render it inside the `lineageQuery.data?.family` block, right after the `RootCausePanel`:

```tsx
import { FamilyLabelControl } from "@/components/autopilot/FamilyLabelControl";
```
```tsx
              {lineageQuery.data?.family && (
                <RootCausePanel
                  key={lineageQuery.data.family.id}
                  token={accessToken!}
                  defectId={lineageQuery.data.family.id}
                />
              )}
              {lineageQuery.data?.family && (
                <FamilyLabelControl key={`label-${lineageQuery.data.family.id}`} familyId={lineageQuery.data.family.id} />
              )}
```

- [ ] **Step 5: Run, expect PASS**

Run: `npm --prefix frontend test -- --run FamilyLabelControl` → PASS. Then the full suite + types: `npm --prefix frontend test` → green and `npm --prefix frontend exec tsc -- --noEmit` → clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/autopilot/FamilyLabelControl.tsx frontend/src/components/autopilot/__tests__/FamilyLabelControl.test.tsx frontend/src/app/app/defects/page.tsx
git commit -m "feat(ui): FamilyLabelControl (etiquetar familia → calibrar) en Defect DNA

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **El lazo cerrado en la UI:** etiquetar una familia en Defect DNA → calibra el motor (R0) → la página Calibración muestra cómo sube la precisión por cliente.
- **`currentLabel` omitido:** `DefectLineageResponse.family` no trae `label`; el selector inicia en `"unknown"`. Mostrar el label actual es follow-up (requiere añadir `label` a `DefectFamilySummary` en el backend).
- **e2e:** requiere #22 (calibración backend) y #23 (F5b-1) en `main`; los tests aquí usan mocks.
- **Fuera de alcance:** bandeja global (F5b-3); historial de correcciones; gráfica de tendencia. **F6** = la demo.
