# F5b-1 — Frontend: vista del run — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una página `/app/autopilot` que recorre, para un run, el flujo de 3 actos (triaje → acción Nivel 2 approve/reject → certificado → gate), consumiendo endpoints ya en `main`.

**Architecture:** Frontend Next.js 16 (App Router). Replica el patrón existente: route handlers proxy (`proxyToBackend`) → `apiRequest` → funciones en `endpoints.ts` → componentes con TanStack Query. Página `"use client"` que orquesta `runId`; cinco componentes enfocados en `components/autopilot/`.

**Tech Stack:** TypeScript, Next.js 16 App Router, Tailwind v4, TanStack Query v5, Vitest + Testing Library. Todo bajo `frontend/`.

## Global Constraints

- **Patrón API:** `apiRequest<T>(path, method, { token, body })` (lanza `ApiClientError`); route handlers `proxyToBackend(request, "/v2/...", { method, body?, contentType? })` (forwardea `Authorization`).
- **`GET /v2/actions` NO acepta `run_id`** — requiere `org_id` (query) + `status` opcional; el filtrado por `run_id` es **client-side** sobre `ActionItem.run_id`.
- **Contratos backend (verbatim):** `TriageVerdict {id, failure_id, category, confidence, rule_applied, requires_approval, llm_assisted, status, evidence_bundle?}` (no hay `test_name`); `ActionItem {id, triage_verdict_id, run_id, org_id?, kind, payload?, summary?, status, artifact_ref?, approved_by?, approved_at?, reject_reason?}`; `ProposeActionsResult {quarantine, ticket, self_heal, skipped}`; `ActionApproveResult {approved, materialized, artifact_ref?}`; `ActionRejectResult {rejected}`; `Certificate {run_id, verdict, risk_score, canonical_json, signature, created_at?}`; `GateResult {verdict, conclusion, check_run_url}`.
- **Auth:** `useAuth()` → `accessToken`; queries `enabled: Boolean(accessToken && runId)`; mutations pasan el token.
- **UI en español**, componentes `@/components/ui/*` (Card, Badge, Button, Input, Label, Skeleton, Textarea), estilo Tailwind `zinc`/`text-sm` (como `assurance/page.tsx`).
- **Tests:** Vitest desde `frontend/` (`npm test` = `vitest run`); mocks (sin red/backend).
- Commits `feat:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## File Structure

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `frontend/src/lib/api/types.ts` | modificar | tipos de Autopilot |
| `frontend/src/lib/api/endpoints.ts` | modificar | 8 funciones de Autopilot |
| `frontend/src/app/api/v2/triage/run/[run_id]/route.ts` | crear | proxy GET triaje |
| `frontend/src/app/api/v2/actions/route.ts` | crear | proxy GET acciones |
| `frontend/src/app/api/v2/actions/run/[run_id]/propose/route.ts` | crear | proxy POST propose |
| `frontend/src/app/api/v2/actions/[action_id]/approve/route.ts` | crear | proxy POST approve |
| `frontend/src/app/api/v2/actions/[action_id]/reject/route.ts` | crear | proxy POST reject |
| `frontend/src/app/api/v2/certificates/run/[run_id]/route.ts` | crear | proxy POST generar cert |
| `frontend/src/app/api/v2/certificates/[run_id]/route.ts` | crear | proxy GET cert |
| `frontend/src/app/api/v2/gate/run/[run_id]/route.ts` | crear | proxy POST gate |
| `frontend/src/lib/api/__tests__/autopilot-endpoints.test.ts` | crear | tests de endpoints |
| `frontend/src/app/app/autopilot/page.tsx` | crear | página orquestadora |
| `frontend/src/components/autopilot/RunSelector.tsx` | crear | seleccionar run |
| `frontend/src/components/autopilot/TriageVerdictList.tsx` | crear | veredictos |
| `frontend/src/components/autopilot/ActionsPanel.tsx` | crear | acciones approve/reject |
| `frontend/src/components/autopilot/CertificateCard.tsx` | crear | certificado |
| `frontend/src/components/autopilot/GateCard.tsx` | crear | gate |
| `frontend/src/components/layout/sidebar-nav.tsx` | modificar | ítem de nav |
| `frontend/src/components/autopilot/__tests__/*.test.tsx` | crear | tests de componentes |

---

## Task 1: API layer (tipos + endpoints + route handlers)

**Files:** Modify `src/lib/api/types.ts`, `src/lib/api/endpoints.ts`; create the 8 route handlers; create `src/lib/api/__tests__/autopilot-endpoints.test.ts`. (All paths under `frontend/`.)

**Interfaces:**
- Produces: the 7 types and 8 endpoint functions named in Global Constraints, plus `/api/v2/...` proxy routes.

- [ ] **Step 1: Types** — append to `frontend/src/lib/api/types.ts`:

```typescript
export interface TriageVerdict {
  id: string;
  failure_id: string;
  category: string;
  confidence: number;
  rule_applied: string;
  requires_approval: boolean;
  llm_assisted: boolean;
  status: string;
  evidence_bundle?: Record<string, unknown> | null;
}

export interface ActionItem {
  id: string;
  triage_verdict_id: string;
  run_id: string;
  org_id?: string | null;
  kind: string;
  payload?: Record<string, unknown> | null;
  summary?: string | null;
  status: string;
  artifact_ref?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  reject_reason?: string | null;
}

export interface ProposeActionsResult {
  quarantine: number;
  ticket: number;
  self_heal: number;
  skipped: number;
}

export interface ActionApproveResult {
  approved: boolean;
  materialized: boolean;
  artifact_ref?: string | null;
}

export interface ActionRejectResult {
  rejected: boolean;
}

export interface Certificate {
  run_id: string;
  verdict: string;
  risk_score: number;
  canonical_json: Record<string, unknown>;
  signature: string;
  created_at?: string | null;
}

export interface GateResult {
  verdict: string;
  conclusion: string;
  check_run_url: string;
}
```

- [ ] **Step 2: Write the failing endpoint tests** — `frontend/src/lib/api/__tests__/autopilot-endpoints.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getTriageVerdicts, proposeActions, getActions, approveAction, rejectAction,
  generateCertificate, getCertificate, publishGate,
} from "@/lib/api/endpoints";

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

describe("autopilot endpoints", () => {
  it("getTriageVerdicts → GET /api/v2/triage/run/{id} con bearer", async () => {
    const spy = mockFetch([{ id: "v1", failure_id: "f1", category: "real", confidence: 0.85,
      rule_applied: "R4_real_recurrent", requires_approval: false, llm_assisted: false, status: "resolved" }]);
    const out = await getTriageVerdicts("tok", "r1");
    expect(out[0].category).toBe("real");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/triage/run/r1");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("proposeActions → POST /api/v2/actions/run/{id}/propose", async () => {
    const spy = mockFetch({ quarantine: 1, ticket: 0, self_heal: 0, skipped: 0 });
    await proposeActions("tok", "r1");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/actions/run/r1/propose");
    expect(init.method).toBe("POST");
  });

  it("getActions → GET /api/v2/actions con org_id (y status opcional)", async () => {
    const spy = mockFetch([]);
    await getActions("tok", "org-1", "proposed");
    expect(lastCall(spy).url).toBe("/api/v2/actions?org_id=org-1&status=proposed");
  });

  it("approveAction → POST /api/v2/actions/{id}/approve", async () => {
    const spy = mockFetch({ approved: true, materialized: true, artifact_ref: "https://x" });
    const out = await approveAction("tok", "a1");
    expect(out.materialized).toBe(true);
    expect(lastCall(spy).url).toBe("/api/v2/actions/a1/approve");
  });

  it("rejectAction → POST /api/v2/actions/{id}/reject con reason en el body", async () => {
    const spy = mockFetch({ rejected: true });
    await rejectAction("tok", "a1", "falso positivo");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/actions/a1/reject");
    expect(JSON.parse(init.body as string)).toEqual({ reason: "falso positivo" });
  });

  it("generateCertificate → POST; getCertificate → GET /api/v2/certificates/{id}", async () => {
    const spy = mockFetch({ run_id: "r1", verdict: "apto", risk_score: 0, canonical_json: {}, signature: "s" });
    await generateCertificate("tok", "r1");
    expect(lastCall(spy).url).toBe("/api/v2/certificates/run/r1");
    spy.mockClear();
    await getCertificate("tok", "r1");
    expect(lastCall(spy).url).toBe("/api/v2/certificates/r1");
  });

  it("publishGate → POST /api/v2/gate/run/{id}", async () => {
    const spy = mockFetch({ verdict: "no-apto", conclusion: "failure", check_run_url: "https://x" });
    const out = await publishGate("tok", "r1");
    expect(out.conclusion).toBe("failure");
    expect(lastCall(spy).url).toBe("/api/v2/gate/run/r1");
  });
});
```

- [ ] **Step 3: Run, expect FAIL**

Run (from `frontend/`): `npm test -- --run autopilot-endpoints` → FAIL (functions not exported).

- [ ] **Step 4: Endpoint functions** — append to `frontend/src/lib/api/endpoints.ts` (and add the type imports to the existing `import type { ... }` block: `TriageVerdict, ActionItem, ProposeActionsResult, ActionApproveResult, ActionRejectResult, Certificate, GateResult`):

```typescript
export function getTriageVerdicts(token: string, runId: string) {
  return apiRequest<TriageVerdict[]>(
    `/api/v2/triage/run/${encodeURIComponent(runId)}`, "GET", { token });
}

export function proposeActions(token: string, runId: string) {
  return apiRequest<ProposeActionsResult>(
    `/api/v2/actions/run/${encodeURIComponent(runId)}/propose`, "POST", { token });
}

export function getActions(token: string, orgId: string, status?: string) {
  const qs = new URLSearchParams({ org_id: orgId });
  if (status) qs.set("status", status);
  return apiRequest<ActionItem[]>(`/api/v2/actions?${qs.toString()}`, "GET", { token });
}

export function approveAction(token: string, actionId: string) {
  return apiRequest<ActionApproveResult>(
    `/api/v2/actions/${encodeURIComponent(actionId)}/approve`, "POST", { token });
}

export function rejectAction(token: string, actionId: string, reason = "") {
  return apiRequest<ActionRejectResult>(
    `/api/v2/actions/${encodeURIComponent(actionId)}/reject`, "POST", { token, body: { reason } });
}

export function generateCertificate(token: string, runId: string) {
  return apiRequest<Certificate>(
    `/api/v2/certificates/run/${encodeURIComponent(runId)}`, "POST", { token });
}

export function getCertificate(token: string, runId: string) {
  return apiRequest<Certificate>(
    `/api/v2/certificates/${encodeURIComponent(runId)}`, "GET", { token });
}

export function publishGate(token: string, runId: string) {
  return apiRequest<GateResult>(
    `/api/v2/gate/run/${encodeURIComponent(runId)}`, "POST", { token });
}
```

- [ ] **Step 5: Route handlers** — create each file (note `params` is a Promise in Next 16, per the existing `assurance/run/[run_id]/route.ts`):

`src/app/api/v2/triage/run/[run_id]/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/triage/run/${encodeURIComponent(run_id)}`, { method: "GET" });
}
```

`src/app/api/v2/actions/route.ts` (forward the query string):
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, `/v2/actions${request.nextUrl.search}`, { method: "GET" });
}
```

`src/app/api/v2/actions/run/[run_id]/propose/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/actions/run/${encodeURIComponent(run_id)}/propose`, { method: "POST" });
}
```

`src/app/api/v2/actions/[action_id]/approve/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ action_id: string }> }) {
  const { action_id } = await params;
  return proxyToBackend(request, `/v2/actions/${encodeURIComponent(action_id)}/approve`, { method: "POST" });
}
```

`src/app/api/v2/actions/[action_id]/reject/route.ts` (has a JSON body):
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ action_id: string }> }) {
  const { action_id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/actions/${encodeURIComponent(action_id)}/reject`,
    { method: "POST", body, contentType: "application/json" });
}
```

`src/app/api/v2/certificates/run/[run_id]/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/certificates/run/${encodeURIComponent(run_id)}`, { method: "POST" });
}
```

`src/app/api/v2/certificates/[run_id]/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/certificates/${encodeURIComponent(run_id)}`, { method: "GET" });
}
```

`src/app/api/v2/gate/run/[run_id]/route.ts`:
```typescript
import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/gate/run/${encodeURIComponent(run_id)}`, { method: "POST" });
}
```

- [ ] **Step 6: Run, expect PASS**

Run (from `frontend/`): `npm test -- --run autopilot-endpoints` → PASS (7 tests). Then `npx tsc --noEmit` → no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/api/types.ts frontend/src/lib/api/endpoints.ts frontend/src/app/api/v2 frontend/src/lib/api/__tests__/autopilot-endpoints.test.ts
git commit -m "feat(ui): API layer de Autopilot (tipos + endpoints + route handlers proxy)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: Página + lectura (RunSelector, TriageVerdictList, nav)

**Files:** Create `src/app/app/autopilot/page.tsx`, `src/components/autopilot/RunSelector.tsx`, `src/components/autopilot/TriageVerdictList.tsx`, `src/components/autopilot/__tests__/TriageVerdictList.test.tsx`; modify `src/components/layout/sidebar-nav.tsx`.

**Interfaces:**
- Consumes: `getTriageVerdicts`, `ingestReport`, `getOrganizations` (Task 1 + existing).
- Produces: `RunSelector` (`{ onRunId: (id: string) => void }`), `TriageVerdictList` (`{ runId: string }`), the `/app/autopilot` route.

- [ ] **Step 1: Nav item** — in `src/components/layout/sidebar-nav.tsx`, import an icon and add the entry. Change the `lucide-react` import to include `Bot`, and add to `navItems` after the Assurance line:

```typescript
  { href: "/app/autopilot", label: "Autopilot", icon: Bot },
```

- [ ] **Step 2: Write the failing test** — `src/components/autopilot/__tests__/TriageVerdictList.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({ getTriageVerdicts: vi.fn() }));

import { getTriageVerdicts } from "@/lib/api/endpoints";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("TriageVerdictList", () => {
  it("muestra los veredictos con su categoría", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "v1", failure_id: "f1", category: "real", confidence: 0.85,
        rule_applied: "R4_real_recurrent", requires_approval: false, llm_assisted: false, status: "resolved" },
    ]);
    renderWithClient(<TriageVerdictList runId="r1" />);
    expect(await screen.findByText("real")).toBeInTheDocument();
    expect(screen.getByText(/R4_real_recurrent/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run, expect FAIL**

Run (from `frontend/`): `npm test -- --run TriageVerdictList` → FAIL (component missing).

- [ ] **Step 4: TriageVerdictList** — `src/components/autopilot/TriageVerdictList.tsx`:

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getTriageVerdicts } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const CATEGORY_STYLE: Record<string, string> = {
  real: "bg-red-100 text-red-700",
  flaky: "bg-amber-100 text-amber-700",
  maintenance: "bg-blue-100 text-blue-700",
  infra: "bg-zinc-200 text-zinc-700",
  unknown: "bg-zinc-100 text-zinc-500",
};

export function TriageVerdictList({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const query = useQuery({
    queryKey: ["triage", runId],
    queryFn: () => getTriageVerdicts(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
  });

  if (query.isLoading) return <Skeleton className="h-24 w-full" />;
  if (query.isError) return <Card className="p-5"><p className="text-sm text-red-600">No se pudieron cargar los veredictos.</p></Card>;

  const verdicts = query.data ?? [];
  return (
    <Card className="space-y-3 p-5">
      <h2 className="text-sm font-medium text-zinc-700">Veredictos de triaje</h2>
      {verdicts.length === 0 ? (
        <p className="text-sm text-zinc-500">Sin veredictos para este run.</p>
      ) : (
        <ul className="space-y-2">
          {verdicts.map((v) => (
            <li key={v.id} className="flex items-center justify-between text-sm">
              <span className="font-mono text-xs text-zinc-500">{v.failure_id.slice(0, 8)}</span>
              <span className="flex items-center gap-2">
                <Badge className={CATEGORY_STYLE[v.category] ?? CATEGORY_STYLE.unknown}>{v.category}</Badge>
                <span className="text-zinc-500">{(v.confidence * 100).toFixed(0)}%</span>
                <span className="text-zinc-400">{v.rule_applied}</span>
                {v.requires_approval && <Badge className="bg-amber-100 text-amber-700">requiere aprobación</Badge>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
```

- [ ] **Step 5: RunSelector** — `src/components/autopilot/RunSelector.tsx`:

```tsx
"use client";

import { useState } from "react";

import { useAuth } from "@/components/providers/auth-provider";
import { ingestReport } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function RunSelector({ orgId, onRunId }: { orgId: string; onRunId: (id: string) => void }) {
  const { accessToken } = useAuth();
  const [project, setProject] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [manualId, setManualId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file || !orgId) {
      setError("Falta archivo u organización.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("project", project || "default");
    form.append("source", "auto");
    form.append("org_id", orgId);
    setSubmitting(true);
    try {
      const res = await ingestReport(accessToken!, form);
      onRunId(res.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al ingerir el reporte.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="max-w-xl space-y-4 p-5">
      <form onSubmit={handleUpload} className="space-y-4">
        <div className="space-y-1">
          <Label htmlFor="project">Proyecto</Label>
          <Input id="project" value={project} onChange={(e) => setProject(e.target.value)} placeholder="cliente-a" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="file">Reporte de test</Label>
          <Input id="file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={submitting}>{submitting ? "Procesando…" : "Analizar run"}</Button>
      </form>
      <div className="flex items-end gap-2 border-t border-zinc-100 pt-4">
        <div className="flex-1 space-y-1">
          <Label htmlFor="manual">…o pega un run_id</Label>
          <Input id="manual" value={manualId} onChange={(e) => setManualId(e.target.value)} placeholder="uuid del run" />
        </div>
        <Button variant="ghost" type="button" disabled={!manualId} onClick={() => onRunId(manualId.trim())}>Cargar</Button>
      </div>
    </Card>
  );
}
```

- [ ] **Step 6: Page** — `src/app/app/autopilot/page.tsx` (Task 3 adds the action components; for now it renders selector + triage):

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getOrganizations } from "@/lib/api/endpoints";
import { RunSelector } from "@/components/autopilot/RunSelector";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";

export default function AutopilotPage() {
  const { accessToken } = useAuth();
  const [runId, setRunId] = useState<string | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["organizations", accessToken],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgId = orgsQuery.data?.[0]?.id ?? "";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Autopilot</h1>
        <p className="text-sm text-zinc-500">Triaje, acción Nivel 2, certificado y gate de un run.</p>
      </div>
      <RunSelector orgId={orgId} onRunId={setRunId} />
      {runId && (
        <div className="space-y-4">
          <TriageVerdictList runId={runId} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Run, expect PASS**

Run (from `frontend/`): `npm test -- --run TriageVerdictList` → PASS. Then `npx tsc --noEmit` → clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/app/autopilot frontend/src/components/autopilot frontend/src/components/layout/sidebar-nav.tsx
git commit -m "feat(ui): página Autopilot + RunSelector + TriageVerdictList + nav

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Acción (ActionsPanel, CertificateCard, GateCard)

**Files:** Create `src/components/autopilot/ActionsPanel.tsx`, `CertificateCard.tsx`, `GateCard.tsx`, and their tests under `src/components/autopilot/__tests__/`; modify `src/app/app/autopilot/page.tsx` to render them.

**Interfaces:**
- Consumes: `proposeActions`, `getActions`, `approveAction`, `rejectAction`, `generateCertificate`, `getCertificate`, `publishGate` (Task 1).
- Produces: `ActionsPanel` (`{ runId: string; orgId: string }`), `CertificateCard` (`{ runId: string }`), `GateCard` (`{ runId: string }`).

- [ ] **Step 1: Write the failing test** — `src/components/autopilot/__tests__/ActionsPanel.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  getActions: vi.fn(), proposeActions: vi.fn(), approveAction: vi.fn(), rejectAction: vi.fn(),
}));

import { getActions, approveAction } from "@/lib/api/endpoints";
import { ActionsPanel } from "@/components/autopilot/ActionsPanel";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ActionsPanel", () => {
  it("muestra solo las acciones del run y aprueba una propuesta", async () => {
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "ticket", summary: "Bug X", status: "proposed" },
      { id: "a2", triage_verdict_id: "v2", run_id: "OTHER", kind: "quarantine", summary: "Otro", status: "proposed" },
    ]);
    (approveAction as ReturnType<typeof vi.fn>).mockResolvedValue({ approved: true, materialized: true, artifact_ref: "https://gh/1" });
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);
    expect(await screen.findByText("Bug X")).toBeInTheDocument();
    expect(screen.queryByText("Otro")).not.toBeInTheDocument(); // filtrado por run_id
    fireEvent.click(screen.getByRole("button", { name: /aprobar/i }));
    await waitFor(() => expect(approveAction).toHaveBeenCalledWith("tok", "a1"));
  });
});
```

- [ ] **Step 2: Run, expect FAIL**

Run (from `frontend/`): `npm test -- --run ActionsPanel` → FAIL (component missing).

- [ ] **Step 3: ActionsPanel** — `src/components/autopilot/ActionsPanel.tsx`:

```tsx
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { getActions, proposeActions, approveAction, rejectAction } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function ActionsPanel({ runId, orgId }: { runId: string; orgId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ["actions", orgId, runId];

  const query = useQuery({
    queryKey: key,
    queryFn: async () => (await getActions(accessToken!, orgId)).filter((a) => a.run_id === runId),
    enabled: Boolean(accessToken && orgId && runId),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: key });
  const propose = useMutation({
    mutationFn: () => proposeActions(accessToken!, runId),
    onSuccess: () => { toast.success("Acciones propuestas."); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const approve = useMutation({
    mutationFn: (id: string) => approveAction(accessToken!, id),
    onSuccess: () => { toast.success("Acción aprobada."); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const reject = useMutation({
    mutationFn: (id: string) => rejectAction(accessToken!, id),
    onSuccess: () => { toast.success("Acción rechazada."); invalidate(); },
    onError: (e: Error) => toast.error(e.message),
  });

  const actions = query.data ?? [];
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700">Acciones (Nivel 2)</h2>
        <Button size="sm" variant="ghost" disabled={propose.isPending} onClick={() => propose.mutate()}>
          {propose.isPending ? "Proponiendo…" : "Proponer acciones"}
        </Button>
      </div>
      {actions.length === 0 ? (
        <p className="text-sm text-zinc-500">Sin acciones para este run.</p>
      ) : (
        <ul className="space-y-2">
          {actions.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="flex-1">
                <Badge>{a.kind}</Badge> <span className="text-zinc-700">{a.summary}</span>
              </span>
              {a.status === "proposed" ? (
                <span className="flex gap-2">
                  <Button size="sm" disabled={approve.isPending} onClick={() => approve.mutate(a.id)}>Aprobar</Button>
                  <Button size="sm" variant="ghost" disabled={reject.isPending} onClick={() => reject.mutate(a.id)}>Rechazar</Button>
                </span>
              ) : a.artifact_ref ? (
                <a className="text-blue-600 underline" href={a.artifact_ref} target="_blank" rel="noreferrer">{a.status}</a>
              ) : (
                <Badge>{a.status}</Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: CertificateCard** — `src/components/autopilot/CertificateCard.tsx`:

```tsx
"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { generateCertificate, getCertificate } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function CertificateCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const key = ["certificate", runId];
  const query = useQuery({
    queryKey: key,
    queryFn: () => getCertificate(accessToken!, runId),
    enabled: Boolean(accessToken && runId),
    retry: false,
  });
  const generate = useMutation({
    mutationFn: () => generateCertificate(accessToken!, runId),
    onSuccess: () => { toast.success("Certificado generado."); qc.invalidateQueries({ queryKey: key }); },
    onError: (e: Error) => toast.error(e.message),
  });

  const cert = query.data;
  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700">Release Assurance Certificate</h2>
        <Button size="sm" variant="ghost" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? "Generando…" : "Generar certificado"}
        </Button>
      </div>
      {cert ? (
        <div className="space-y-1 text-sm text-zinc-600">
          <div className="flex items-center gap-2">
            <Badge>{cert.verdict}</Badge>
            <span>risk score <strong className="text-zinc-900">{cert.risk_score}</strong></span>
          </div>
          <p className="font-mono text-xs text-zinc-400 break-all">firma: {cert.signature.slice(0, 32)}…</p>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">Aún no hay certificado para este run.</p>
      )}
    </Card>
  );
}
```

- [ ] **Step 5: GateCard** — `src/components/autopilot/GateCard.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/providers/auth-provider";
import { publishGate } from "@/lib/api/endpoints";
import type { GateResult } from "@/lib/api/types";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const CONCLUSION_STYLE: Record<string, string> = {
  success: "bg-green-100 text-green-700",
  neutral: "bg-zinc-200 text-zinc-700",
  failure: "bg-red-100 text-red-700",
};

export function GateCard({ runId }: { runId: string }) {
  const { accessToken } = useAuth();
  const [result, setResult] = useState<GateResult | null>(null);
  const publish = useMutation({
    mutationFn: () => publishGate(accessToken!, runId),
    onSuccess: (r) => { setResult(r); toast.success(`Gate: ${r.conclusion}`); },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card className="space-y-3 p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-zinc-700">Gate (check run)</h2>
        <Button size="sm" variant="ghost" disabled={publish.isPending} onClick={() => publish.mutate()}>
          {publish.isPending ? "Publicando…" : "Publicar gate"}
        </Button>
      </div>
      {result ? (
        <div className="flex items-center gap-2 text-sm text-zinc-600">
          <Badge className={CONCLUSION_STYLE[result.conclusion] ?? CONCLUSION_STYLE.neutral}>{result.conclusion}</Badge>
          <span>{result.verdict}</span>
          <a className="text-blue-600 underline" href={result.check_run_url} target="_blank" rel="noreferrer">ver check run</a>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">Publica el gate para ver el resultado.</p>
      )}
    </Card>
  );
}
```

- [ ] **Step 6: Wire them into the page** — in `src/app/app/autopilot/page.tsx`, add the imports and render them inside the `{runId && (...)}` block after `TriageVerdictList`:

```tsx
import { ActionsPanel } from "@/components/autopilot/ActionsPanel";
import { CertificateCard } from "@/components/autopilot/CertificateCard";
import { GateCard } from "@/components/autopilot/GateCard";
```
```tsx
          <TriageVerdictList runId={runId} />
          <ActionsPanel runId={runId} orgId={orgId} />
          <CertificateCard runId={runId} />
          <GateCard runId={runId} />
```

- [ ] **Step 7: Run, expect PASS**

Run (from `frontend/`): `npm test -- --run ActionsPanel` → PASS. Then the full suite + types: `npm test` → green and `npx tsc --noEmit` → clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/autopilot frontend/src/app/app/autopilot/page.tsx
git commit -m "feat(ui): ActionsPanel (approve/reject) + CertificateCard + GateCard

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **El lazo visible:** subir un run → ver veredictos → proponer acciones → aprobar (→ Issue/PR real en GitHub) → generar certificado → publicar gate (🔴→🟢). La demo de 3 actos en una pantalla.
- **Verificación manual (post-merge):** con el backend on-premise corriendo y `NEXT_PUBLIC_API_BASE_URL` apuntando a él.
- **Motivo de rechazo:** F5b-1 envía `reason=""` (el endpoint lo acepta vacío); un campo de texto para el motivo es follow-up (el spec lo marcó "opcional").
- **Fuera de alcance:** bandeja global + foso (métricas/etiquetado) = **F5b-2**; HTML imprimible del cert; lista de runs.
