# UX · Sub-proyecto A (Orientación + Navegación) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar al usuario un punto de partida (dashboard con checklist) y un mapa (sidebar agrupado en ES), sin tocar la lógica de negocio.

**Architecture:** T1 dashboard `/app` con checklist de setup. T2 extrae la navegación a una fuente única (`nav.ts`) y agrupa el sidebar. T3 usa esa fuente en el topbar + idioma/identidad. T4 empty-states con CTA en las páginas del lazo.

**Tech Stack:** Next.js (App Router) · TypeScript · shadcn-style UI · TanStack Query · vitest.

## Global Constraints

- **Identidad:** el producto es **Mnemo** (descriptor "continuidad de QA"); footer y textos de marca usan "Mnemo" (no "QA Autopilot").
- **Idioma:** UI en español, `lang="es"`. Se MANTIENEN los nombres de marca de feature: Assurance, Autopilot, Defect DNA, Knowledge Graph, Onboarding. Se traducen: Integrations→**Integraciones**, Organization→**Organización**, Settings→**Ajustes**, "Sign out"→**Cerrar sesión**.
- **Patrón de datos** (copiar EXACTO): `const { accessToken } = useAuth();` + `const { activeOrgId, isLoading: orgLoading } = useActiveOrg();` + `useQuery({ queryKey:[k, orgId], queryFn:()=>client(accessToken!, {org_id: orgId}), enabled: Boolean(accessToken && orgId) })`. `useAuth` expone `accessToken/user/signOut`; `useActiveOrg` expone `activeOrgId/isLoading`.
- **No romper lógica**: solo navegación, una página nueva y textos. Las queries del dashboard son de lectura y degradan (paso "pendiente" si fallan).
- **Verificación local = CI por tarea:** `npm run lint:ci` + `npm test` + `npx tsc --noEmit` + `npm run build` (desde `frontend/`). Si node_modules se corrompe (iCloud: "Minimatch is not a constructor"/"Invalid package config undici") → `npm --prefix frontend ci`. **No git worktree.** Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Dashboard `/app` + `SetupChecklist`

**Files:** Create `frontend/src/components/dashboard/SetupChecklist.tsx`; Modify `frontend/src/app/app/page.tsx` (hoy solo `redirect`); Test `frontend/src/components/dashboard/__tests__/SetupChecklist.test.tsx` + `frontend/src/app/app/__tests__/dashboard.test.tsx`.

**Interfaces:** Produces — `SetupChecklist({ steps, loading })` con `type SetupStep = { n: number; title: string; description: string; href: string; cta: string; done: boolean; highlight?: boolean }`.

- [ ] **Step 1: Write the failing test** for `SetupChecklist` (presentacional, sin red): con `steps=[{n:1,title:"Conecta GitHub",description:"d",href:"/app/integrations",cta:"Configurar",done:true}, {n:2,...,done:false}]` → el paso done muestra el check (`data-testid="step-done-1"`), el pendiente muestra `data-testid="step-todo-2"`, y cada CTA es un enlace al `href`. Con `loading` → muestra `data-testid="checklist-skeleton"`.

- [ ] **Step 2: Run, expect FAIL.** `npm --prefix frontend test -- SetupChecklist`

- [ ] **Step 3: Implement** `frontend/src/components/dashboard/SetupChecklist.tsx`:
```tsx
import Link from "next/link";
import { Check, Circle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export type SetupStep = {
  n: number; title: string; description: string;
  href: string; cta: string; done: boolean; highlight?: boolean;
};

export function SetupChecklist({ steps, loading }: { steps: SetupStep[]; loading?: boolean }) {
  if (loading) {
    return (
      <div data-testid="checklist-skeleton" className="space-y-3">
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
      </div>
    );
  }
  return (
    <ol className="space-y-3">
      {steps.map((s) => (
        <li key={s.n}>
          <Card className={`flex items-center gap-4 p-4 ${s.highlight ? "border-zinc-900" : ""}`}>
            <span
              data-testid={s.done ? `step-done-${s.n}` : `step-todo-${s.n}`}
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${s.done ? "bg-emerald-100 text-emerald-700" : "bg-zinc-100 text-zinc-400"}`}
              aria-label={s.done ? "Completado" : "Pendiente"}
            >
              {s.done ? <Check size={16} /> : <Circle size={16} />}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-zinc-900">{s.n}. {s.title}</p>
              <p className="text-xs text-zinc-500">{s.description}</p>
            </div>
            <Button asChild variant={s.highlight ? "default" : "outline"} size="sm">
              <Link href={s.href}>{s.cta}</Link>
            </Button>
          </Card>
        </li>
      ))}
    </ol>
  );
}
```
(Si `Button` no soporta `asChild`, usar `<Link className={buttonVariants(...)}>` o un `<Link>` estilado; comprobar `components/ui/button.tsx` y adaptarse a su API.)

- [ ] **Step 4: Run PASS.** `npm --prefix frontend test -- SetupChecklist`

- [ ] **Step 5: Write the failing test** for the dashboard page (`dashboard.test.tsx`): mock `@/components/providers/auth-provider` (`useAuth`→`{accessToken:"t"}`), `@/components/providers/org-provider` (`useActiveOrg`→`{activeOrgId:"o1", isLoading:false}`) y los clientes `@/lib/api/endpoints` (`getGithubConfig`→`{configured:true}`, `listRepoTests`→`[{path:"a"}]`, `listKnowledge`→`[]`, `getGaps`→`[]`) con un `QueryClientProvider` real. Asserts: paso 1 y 2 ✓ (`step-done-1`, `step-done-2`), paso 3 y 4 ○; un caso con `useActiveOrg`→`{activeOrgId:"", isLoading:false}` muestra el empty-state con enlace a `/app/org`.

- [ ] **Step 6: Implement** `frontend/src/app/app/page.tsx` (reemplaza el `redirect`):
```tsx
"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/components/providers/auth-provider";
import { useActiveOrg } from "@/components/providers/org-provider";
import { getGithubConfig, listRepoTests, listKnowledge, getGaps } from "@/lib/api/endpoints";
import { SetupChecklist, type SetupStep } from "@/components/dashboard/SetupChecklist";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const { accessToken } = useAuth();
  const { activeOrgId, isLoading: orgLoading } = useActiveOrg();
  const orgId = activeOrgId || "";
  const enabled = Boolean(accessToken && orgId);
  const opts = { enabled, retry: false } as const;

  const github = useQuery({ queryKey: ["github-config", orgId], queryFn: () => getGithubConfig(accessToken!, { org_id: orgId }), ...opts });
  const repo = useQuery({ queryKey: ["repo-tests", orgId], queryFn: () => listRepoTests(accessToken!, { org_id: orgId }), ...opts });
  const knowledge = useQuery({ queryKey: ["knowledge", orgId], queryFn: () => listKnowledge(accessToken!, orgId), ...opts });
  const gaps = useQuery({ queryKey: ["gaps", orgId], queryFn: () => getGaps(accessToken!, { org_id: orgId }), ...opts });

  if (!orgLoading && !orgId) {
    return (
      <Card className="p-6">
        <p className="text-sm text-zinc-700">Crea o únete a una organización para empezar.</p>
        <Button asChild className="mt-3"><Link href="/app/org">Ir a Organización</Link></Button>
      </Card>
    );
  }

  const steps: SetupStep[] = [
    { n: 1, title: "Conecta GitHub", description: "Enlaza el repositorio de tu equipo.", href: "/app/integrations", cta: "Configurar", done: Boolean(github.data?.configured) },
    { n: 2, title: "Indexa los tests de tu repo", description: "Mnemo aprende el estilo de tus pruebas reales.", href: "/app/integrations", cta: "Indexar", done: (repo.data?.length ?? 0) > 0 },
    { n: 3, title: "Captura conocimiento de QA", description: "Reglas, lecciones y riesgos de tu producto.", href: "/app/knowledge", cta: "Capturar", done: (knowledge.data?.length ?? 0) > 0 },
    { n: 4, title: "Revisa tus gaps de cobertura", description: "Reglas sin un test que las cubra.", href: "/app/graph", cta: "Ver gaps", done: (gaps.data?.length ?? 0) > 0 },
    { n: 5, title: "Genera el test que falta", description: "Desde un gap, al estilo de tu repo, hacia un PR.", href: "/app/graph", cta: "Generar", done: false, highlight: true },
  ];
  const loading = orgLoading || github.isLoading || repo.isLoading || knowledge.isLoading || gaps.isLoading;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-zinc-900">Pon Mnemo en marcha</h2>
        <p className="text-sm text-zinc-500">Sigue estos pasos para activar la continuidad de QA.</p>
      </div>
      <SetupChecklist steps={steps} loading={loading} />
      <div className="grid gap-3 sm:grid-cols-3">
        {[["Conocimiento", "/app/knowledge"], ["Knowledge Graph", "/app/graph"], ["Plan de pruebas", "/app/test-plan"]].map(([label, href]) => (
          <Button key={href} asChild variant="outline"><Link href={href}>{label}</Link></Button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Run PASS** + the full CI gate (`lint:ci`+`test`+`tsc`+`build`).
- [ ] **Step 8: Commit** `feat(ux): dashboard /app con checklist de setup` + trailer.

---

## Task 2: Navegación como fuente única + sidebar agrupado

**Files:** Create `frontend/src/components/layout/nav.ts`; Modify `frontend/src/components/layout/sidebar-nav.tsx`; Test `frontend/src/components/layout/__tests__/sidebar-nav.test.tsx`.

**Interfaces:** Produces — `nav.ts`: `NAV_SECTIONS: { title: string | null; items: NavItem[] }[]` con `type NavItem = { href: string; label: string; icon: LucideIcon }`, y `labelForPath(pathname: string): string | null`.

- [ ] **Step 1: Write the failing test** (`sidebar-nav.test.tsx`, render con un mock de `usePathname`): aparecen los 4 encabezados de sección ("Continuidad", "Aseguramiento", "Configuración") + el item "Dashboard"; hay 12 enlaces con los labels ES (incluye "Integraciones", "Organización", "Ajustes", y "Dashboard"); con `usePathname`→`/app/integrations` el enlace de Integraciones está activo y el de Dashboard NO; con `usePathname`→`/app` el de Dashboard SÍ.

- [ ] **Step 2: Run, expect FAIL.** `npm --prefix frontend test -- sidebar-nav`

- [ ] **Step 3: Implement** `frontend/src/components/layout/nav.ts`:
```ts
import { Bot, BrainCircuit, Building2, ClipboardList, Dna, GraduationCap, Gauge, LayoutDashboard, Network, Plug, Settings, ShieldCheck, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };
export type NavSection = { title: string | null; items: NavItem[] };

export const NAV_SECTIONS: NavSection[] = [
  { title: null, items: [{ href: "/app", label: "Dashboard", icon: LayoutDashboard }] },
  { title: "Continuidad", items: [
    { href: "/app/knowledge", label: "Conocimiento", icon: BrainCircuit },
    { href: "/app/onboarding", label: "Onboarding", icon: GraduationCap },
    { href: "/app/graph", label: "Knowledge Graph", icon: Network },
    { href: "/app/test-plan", label: "Plan de pruebas", icon: ClipboardList },
  ]},
  { title: "Aseguramiento", items: [
    { href: "/app/assurance", label: "Assurance", icon: ShieldCheck },
    { href: "/app/autopilot", label: "Autopilot", icon: Bot },
    { href: "/app/defects", label: "Defect DNA", icon: Dna },
    { href: "/app/calibration", label: "Calibración", icon: Gauge },
  ]},
  { title: "Configuración", items: [
    { href: "/app/integrations", label: "Integraciones", icon: Plug },
    { href: "/app/org", label: "Organización", icon: Building2 },
    { href: "/app/settings", label: "Ajustes", icon: Settings },
  ]},
];

export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export function labelForPath(pathname: string): string | null {
  return NAV_ITEMS.find((i) => i.href === pathname)?.label ?? null;
}
```

- [ ] **Step 4: Implement** `sidebar-nav.tsx` — consumir `NAV_SECTIONS`, renderizar cada sección con su encabezado, el logo enlaza a `/app`, footer "Mnemo · continuidad de QA · privado · on-premise". El `active` por match EXACTO (`pathname === item.href`):
```tsx
import { NAV_SECTIONS } from "@/components/layout/nav";
// ...logo: <Link href="/app" ...>  (icono actual; el texto "Mnemo")
<nav className="space-y-4 px-3">
  {NAV_SECTIONS.map((section) => (
    <div key={section.title ?? "home"} className="space-y-1">
      {section.title && <p className="px-3 pt-2 text-xs font-medium uppercase tracking-wide text-zinc-400">{section.title}</p>}
      {section.items.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href;
        return (
          <Link key={item.href} href={item.href} onClick={onClose}
            className={cn("flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition",
              active ? "bg-zinc-900 text-white" : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900")}>
            <Icon size={16} />{item.label}
          </Link>
        );
      })}
    </div>
  ))}
</nav>
// footer: <p className="mt-auto px-5 py-4 text-xs text-zinc-500">Mnemo · continuidad de QA · privado · on-premise</p>
```

- [ ] **Step 5: Run PASS** + CI gate. **Commit** `feat(ux): sidebar agrupado en secciones + fuente única de navegación (ES)` + trailer.

---

## Task 3: Idioma/identidad + topbar desde la fuente única

**Files:** Modify `frontend/src/app/layout.tsx` (lang), `frontend/src/components/layout/topbar.tsx`; Test `frontend/src/components/layout/__tests__/topbar.test.tsx`.

- [ ] **Step 1: Write the failing test** (`topbar.test.tsx`, mock `usePathname`→`/app/integrations`, y `useAuth`→`{user:{email:"a@b.c"}, signOut: vi.fn()}`): el título mostrado es "Integraciones" (antes caía a "Mnemo"); existe un botón "Cerrar sesión".

- [ ] **Step 2: Run, expect FAIL.** `npm --prefix frontend test -- topbar`

- [ ] **Step 3: Implement**:
  - `frontend/src/app/layout.tsx:18` → `<html lang="es">`.
  - `topbar.tsx`: importar `labelForPath` de `@/components/layout/nav`, `const title = labelForPath(pathname) ?? "Mnemo";` (eliminar el `pageTitles` local); quitar el subtítulo fijo jergoso ("Triaje determinista · …") — dejarlo sin subtítulo o uno neutro ("Mnemo"); botón "Sign out" → "Cerrar sesión".

- [ ] **Step 4: Run PASS** + CI gate. **Commit** `feat(ux): idioma ES + identidad Mnemo + topbar desde fuente única` + trailer.

---

## Task 4: Empty-states con CTA en las páginas del lazo

**Files:** Modify `frontend/src/app/app/graph/page.tsx`, `frontend/src/app/app/calibration/page.tsx`, `frontend/src/app/app/onboarding/page.tsx`; Test: extender el test de graph (o crear uno mínimo).

- [ ] **Step 1: Read** los tres empty-states actuales (graph ~163 "Aún no hay conocimiento suficiente"; calibration ~36; onboarding resumen vacío) y localizar el texto exacto.
- [ ] **Step 2: Write/adjust a test** (graph): cuando el grafo está vacío, el empty-state contiene un enlace a `/app/knowledge` (`getByRole("link", { name: /conocimiento/i })`).
- [ ] **Step 3: Implement** — en cada empty-state, añadir bajo el texto un `<Button asChild variant="outline" size="sm"><Link href="...">...</Link></Button>` (o `<Link>` estilado): graph → `/app/knowledge` ("Captura conocimiento"); calibration → `/app/defects` ("Ir a Defect DNA"); onboarding (resumen vacío) → `/app/knowledge` ("Captura conocimiento"). Importar `Link` donde falte. No cambiar la lógica de cuándo se muestra el empty-state.
- [ ] **Step 4: Run** el test + CI gate. **Commit** `feat(ux): empty-states con CTA en las páginas del lazo` + trailer.

---

## Notas de cierre
- **Orden:** T1 (dashboard) → T2 (nav.ts + sidebar) → T3 (topbar usa nav.ts + idioma) → T4 (empty-states). T3 depende de `nav.ts` (creado en T2).
- **Reusa:** shadcn (Card/Button/Skeleton), `useAuth`/`useActiveOrg`, los clientes existentes, lucide.
- **No rompe lógica de negocio:** páginas de datos intactas salvo el empty-state (T4) y la home (T1).
- **Verificación local=CI por tarea** (recordar `npm --prefix frontend ci` si node_modules se corrompe).
- **Fuera de alcance:** B (fuentes, tooltips de jerga, skeletons globales, confirmaciones, Select, a11y del grafo, reordenar Integrations), C (verify público, recorrido del lazo, demo/seed, docs).
