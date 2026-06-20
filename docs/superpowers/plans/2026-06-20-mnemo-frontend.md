# Mnemo — Frontend (Plan 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al frontend Next.js las páginas **Assurance** (subir reporte → veredicto) y **Defect DNA** (familias + linaje), con sus tipos, funciones de cliente y rutas proxy, consumiendo los endpoints `/v2/ingest/report`, `/v2/defects`, `/v2/defects/{id}`, `/v2/assurance/run/{id}`.

**Architecture:** Sigue los patrones existentes: tipos en `lib/api/types.ts`, funciones de cliente en `lib/api/endpoints.ts` (sobre `apiRequest`), rutas proxy finas en `app/api/v2/**` (vía `proxyToBackend`), páginas cliente con `useAuth().accessToken` + TanStack Query. shadcn/ui para UI.

**Tech Stack:** Next.js (App Router) + React + TypeScript + TanStack Query + shadcn/ui + vitest. Branch `feat/mnemo-assurance`. Trabajar en `frontend/`; verificar con `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` (NO `npm run dev` — está bloqueado por hook). `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend`.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/lib/api/types.ts` (extender) | tipos de las respuestas Mnemo |
| `frontend/src/lib/api/endpoints.ts` (extender) | `ingestReport`, `getDefects`, `getDefectLineage`, `getAssuranceVerdict` |
| `frontend/src/app/api/v2/ingest/report/route.ts` | proxy POST multipart |
| `frontend/src/app/api/v2/defects/route.ts` | proxy GET (query org_id) |
| `frontend/src/app/api/v2/defects/[id]/route.ts` | proxy GET linaje |
| `frontend/src/app/api/v2/assurance/run/[run_id]/route.ts` | proxy GET veredicto |
| `frontend/src/app/app/defects/page.tsx` | dashboard Defect DNA |
| `frontend/src/app/app/assurance/page.tsx` | subir reporte → veredicto |
| `frontend/src/components/layout/sidebar-nav.tsx` (extender) | enlaces nuevos |
| `frontend/src/lib/api/__tests__/mnemo-endpoints.test.ts` | test de las funciones de cliente |

---

## Task 1: Tipos + funciones de cliente

**Files:**
- Modify: `frontend/src/lib/api/types.ts`, `frontend/src/lib/api/endpoints.ts`
- Test: `frontend/src/lib/api/__tests__/mnemo-endpoints.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/api/__tests__/mnemo-endpoints.test.ts`:
```typescript
import { afterEach, describe, expect, it, vi } from "vitest";

import { getDefects, getAssuranceVerdict } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

describe("mnemo endpoints", () => {
  it("getDefects calls /api/v2/defects with org_id query and bearer token", async () => {
    const spy = mockFetch([{ id: "f1", title: "T", status: "open", occurrence_count: 2, projects: [] }]);
    const out = await getDefects("tok", "org-1");
    expect(out[0].id).toBe("f1");
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/defects?org_id=org-1");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
  });

  it("getAssuranceVerdict calls /api/v2/assurance/run/{id}", async () => {
    mockFetch({ run_id: "r1", ingested: 1, known: 0, novel: 1, risk: "atencion", top_families: [], narrative: null });
    const out = await getAssuranceVerdict("tok", "r1");
    expect(out.run_id).toBe("r1");
    expect(out.risk).toBe("atencion");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend && npx vitest run src/lib/api/__tests__/mnemo-endpoints.test.ts`
Expected: FAIL — `getDefects`/`getAssuranceVerdict` no existen.

- [ ] **Step 3: Append types to `frontend/src/lib/api/types.ts`**

```typescript
export interface IngestReportResponse {
  run_id: string;
  ingested: number;
  known: number;
  novel: number;
}

export interface DefectFamilyResponse {
  id: string;
  title: string;
  status: string;
  occurrence_count: number;
  first_seen: string | null;
  last_seen: string | null;
  projects: string[];
}

export interface FailureRef {
  id: string;
  test_name: string;
  error_type: string | null;
  project: string;
  source: string;
  created_at: string | null;
}

export interface DefectLineageResponse {
  family: {
    id: string;
    title: string;
    status: string;
    occurrence_count: number;
  } | null;
  failures: FailureRef[];
}

export interface FamilyVerdict {
  id: string;
  title: string;
  occurrence_count: number;
  recurring: boolean;
}

export interface AssuranceVerdictResponse {
  run_id: string;
  ingested: number;
  known: number;
  novel: number;
  risk: string;
  top_families: FamilyVerdict[];
  narrative: string | null;
}
```

- [ ] **Step 4: Append client functions to `frontend/src/lib/api/endpoints.ts`**

Extend the import block to add the new types, then append:
```typescript
export function ingestReport(token: string, payload: FormData) {
  return apiRequest<IngestReportResponse>("/api/v2/ingest/report", "POST", { token, body: payload });
}

export function getDefects(token: string, orgId: string) {
  return apiRequest<DefectFamilyResponse[]>(
    `/api/v2/defects?org_id=${encodeURIComponent(orgId)}`,
    "GET",
    { token },
  );
}

export function getDefectLineage(token: string, defectId: string) {
  return apiRequest<DefectLineageResponse>(
    `/api/v2/defects/${encodeURIComponent(defectId)}`,
    "GET",
    { token },
  );
}

export function getAssuranceVerdict(token: string, runId: string) {
  return apiRequest<AssuranceVerdictResponse>(
    `/api/v2/assurance/run/${encodeURIComponent(runId)}`,
    "GET",
    { token },
  );
}
```
(Add `IngestReportResponse, DefectFamilyResponse, DefectLineageResponse, AssuranceVerdictResponse` to the `import type { ... } from "@/lib/api/types"` block.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend && npx vitest run src/lib/api/__tests__/mnemo-endpoints.test.ts`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add frontend/src/lib/api/types.ts frontend/src/lib/api/endpoints.ts frontend/src/lib/api/__tests__/mnemo-endpoints.test.ts
git commit -m "feat(frontend): add Mnemo API types and client functions"
```

---

## Task 2: Rutas proxy de Next.js

**Files:**
- Create: `frontend/src/app/api/v2/ingest/report/route.ts`, `frontend/src/app/api/v2/defects/route.ts`, `frontend/src/app/api/v2/defects/[id]/route.ts`, `frontend/src/app/api/v2/assurance/run/[run_id]/route.ts`

- [ ] **Step 1: Create `frontend/src/app/api/v2/ingest/report/route.ts`**

```typescript
import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  return proxyToBackend(request, "/v2/ingest/report", {
    method: "POST",
    body: formData,
  });
}
```

- [ ] **Step 2: Create `frontend/src/app/api/v2/defects/route.ts`**

```typescript
import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, `/v2/defects${request.nextUrl.search}`, {
    method: "GET",
  });
}
```

- [ ] **Step 3: Create `frontend/src/app/api/v2/defects/[id]/route.ts`**

```typescript
import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToBackend(request, `/v2/defects/${encodeURIComponent(id)}`, {
    method: "GET",
  });
}
```

- [ ] **Step 4: Create `frontend/src/app/api/v2/assurance/run/[run_id]/route.ts`**

```typescript
import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/assurance/run/${encodeURIComponent(run_id)}`, {
    method: "GET",
  });
}
```

- [ ] **Step 5: Typecheck + lint**

Run: `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend && npm run typecheck && npm run lint`
Expected: sin errores. (Si la firma de `params` no coincide con la versión de Next instalada — algunas versiones usan `params: { id: string }` síncrono — ajustar a la forma que compile; verificar con un route existente como `app/api/v2/orgs/join/route.ts`.)

- [ ] **Step 6: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add frontend/src/app/api/v2/ingest frontend/src/app/api/v2/defects frontend/src/app/api/v2/assurance
git commit -m "feat(frontend): add proxy routes for ingest/defects/assurance"
```

---

## Task 3: Página Defect DNA

**Files:**
- Create: `frontend/src/app/app/defects/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getDefects, getDefectLineage, getOrganizations } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function DefectsPage() {
  const { accessToken } = useAuth();
  const [orgId, setOrgId] = useState<string>("");
  const [selected, setSelected] = useState<string | null>(null);

  const orgsQuery = useQuery({
    queryKey: ["orgs"],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });

  const activeOrg = orgId || orgsQuery.data?.[0]?.id || "";

  const defectsQuery = useQuery({
    queryKey: ["defects", activeOrg],
    queryFn: () => getDefects(accessToken!, activeOrg),
    enabled: Boolean(accessToken && activeOrg),
  });

  const lineageQuery = useQuery({
    queryKey: ["lineage", selected],
    queryFn: () => getDefectLineage(accessToken!, selected!),
    enabled: Boolean(accessToken && selected),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Defect DNA</h1>
        <p className="text-sm text-zinc-500">Familias de defecto y su linaje a través de proyectos.</p>
      </div>

      {orgsQuery.data && orgsQuery.data.length > 1 && (
        <select
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm"
          value={activeOrg}
          onChange={(e) => setOrgId(e.target.value)}
        >
          {orgsQuery.data.map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Familias</h2>
          {defectsQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {defectsQuery.data && defectsQuery.data.length === 0 && (
            <p className="text-sm text-zinc-500">No hay familias todavía. Sube un reporte en Assurance.</p>
          )}
          <ul className="space-y-2">
            {defectsQuery.data?.map((f) => (
              <li key={f.id}>
                <button
                  onClick={() => setSelected(f.id)}
                  className="flex w-full items-center justify-between rounded-lg border border-zinc-200 px-3 py-2 text-left text-sm hover:bg-zinc-50"
                >
                  <span className="font-medium text-zinc-900">{f.title}</span>
                  <span className="flex items-center gap-2">
                    <Badge>{f.occurrence_count}x</Badge>
                    {f.projects.length > 1 && <Badge>{f.projects.length} proyectos</Badge>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-4">
          <h2 className="mb-3 text-sm font-medium text-zinc-700">Linaje</h2>
          {!selected && <p className="text-sm text-zinc-500">Selecciona una familia.</p>}
          {lineageQuery.isLoading && <Skeleton className="h-24 w-full" />}
          {lineageQuery.data?.family && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-zinc-900">{lineageQuery.data.family.title}</p>
              <ul className="space-y-1 text-sm text-zinc-600">
                {lineageQuery.data.failures.map((fl) => (
                  <li key={fl.id} className="flex items-center justify-between">
                    <span>{fl.test_name}</span>
                    <Badge>{fl.project}</Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend && npm run typecheck`
Expected: sin errores. (Si `Badge`/`Card`/`Skeleton` tienen una API distinta, mirar `src/components/ui/*` y ajustar props.)

- [ ] **Step 3: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add frontend/src/app/app/defects/page.tsx
git commit -m "feat(frontend): add Defect DNA dashboard page"
```

---

## Task 4: Página Assurance (subir → veredicto)

**Files:**
- Create: `frontend/src/app/app/assurance/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getAssuranceVerdict, getOrganizations, ingestReport } from "@/lib/api/endpoints";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

export default function AssurancePage() {
  const { accessToken } = useAuth();
  const [project, setProject] = useState("");
  const [source, setSource] = useState("allure");
  const [file, setFile] = useState<File | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const orgsQuery = useQuery({
    queryKey: ["orgs"],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgId = orgsQuery.data?.[0]?.id ?? "";

  const verdictQuery = useQuery({
    queryKey: ["verdict", runId],
    queryFn: () => getAssuranceVerdict(accessToken!, runId!),
    enabled: Boolean(accessToken && runId),
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file || !orgId) {
      setError("Falta archivo u organización.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("project", project || "default");
    form.append("source", source);
    form.append("org_id", orgId);
    setSubmitting(true);
    try {
      const res = await ingestReport(accessToken!, form);
      setRunId(res.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al ingerir el reporte.");
    } finally {
      setSubmitting(false);
    }
  }

  const v = verdictQuery.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Assurance</h1>
        <p className="text-sm text-zinc-500">Sube un reporte de test y obtén el veredicto de aseguramiento.</p>
      </div>

      <Card className="max-w-xl space-y-4 p-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="project">Proyecto</Label>
            <Input id="project" value={project} onChange={(e) => setProject(e.target.value)} placeholder="cliente-a" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="source">Formato</Label>
            <select
              id="source"
              className="w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="allure">Allure (JSON)</option>
              <option value="junit">JUnit (XML)</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="file">Reporte</Label>
            <Input id="file" type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={submitting}>{submitting ? "Procesando…" : "Analizar run"}</Button>
        </form>
      </Card>

      {v && (
        <Card className="max-w-xl space-y-3 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-700">Veredicto del run</h2>
            <Badge>{v.risk === "atencion" ? "Atención" : "OK"}</Badge>
          </div>
          <div className="flex gap-4 text-sm text-zinc-600">
            <span><strong className="text-zinc-900">{v.known}</strong> conocidos</span>
            <span><strong className="text-zinc-900">{v.novel}</strong> nuevos</span>
            <span><strong className="text-zinc-900">{v.ingested}</strong> totales</span>
          </div>
          {v.top_families.length > 0 && (
            <ul className="space-y-1 text-sm text-zinc-600">
              {v.top_families.map((f) => (
                <li key={f.id} className="flex items-center justify-between">
                  <span>{f.title}</span>
                  <span className="flex items-center gap-2">
                    <Badge>{f.occurrence_count}x</Badge>
                    {f.recurring && <Badge>recurrente</Badge>}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {v.narrative && <p className="text-sm text-zinc-700">{v.narrative}</p>}
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend && npm run typecheck`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add frontend/src/app/app/assurance/page.tsx
git commit -m "feat(frontend): add Assurance upload+verdict page"
```

---

## Task 5: Navegación + verificación completa

**Files:**
- Modify: `frontend/src/components/layout/sidebar-nav.tsx`

- [ ] **Step 1: Add nav items**

En `sidebar-nav.tsx`, añadir los iconos al import de `lucide-react` (`ShieldCheck`, `Dna`) y dos entradas al array `navItems` (tras "Analyze"):
```typescript
  { href: "/app/assurance", label: "Assurance", icon: ShieldCheck },
  { href: "/app/defects", label: "Defect DNA", icon: Dna },
```
(Si `Dna` no existe en la versión de lucide-react instalada, usar `Fingerprint` o `Activity`.)

- [ ] **Step 2: Full check**

Run: `cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend && npm run typecheck && npm run lint && npm test && npm run build`
Expected: todo verde (lint con 0 warnings, vitest pasa, build de Next OK).

- [ ] **Step 3: Commit**

```bash
cd /Users/gonzalo/Documents/GitHub/SmartErrorDebugger
git add frontend/src/components/layout/sidebar-nav.tsx
git commit -m "feat(frontend): add Assurance and Defect DNA nav entries"
```

---

## Próximos planes

- **Plan 6:** documentación (`docs/functional`, `docs/technical`, ADR) + poda legacy + `scripts/seed_demo.py`.
