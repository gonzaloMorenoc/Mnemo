# Bloque C · C4 — guion + self-heal en vivo + aislamiento A/B — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el Bloque C: el push en vivo demuestra self-heal de mantenimiento real, la UI deja cambiar de organización (aislamiento A/B), y hay guion + runbook de la demo.

**Architecture:** T1 siembra un green baseline de `test_perfil` para que el push en vivo de `fresh_push` dé R3 maintenance. T2 añade un selector de organización global (provider + switcher + migración de 4 páginas). T3 escribe el guion y el runbook.

**Tech Stack:** Python/pytest (backend); Next.js/TS/vitest (frontend); markdown (docs).

## Global Constraints

- **Self-heal honesto:** el green baseline es un run verde legítimo; el push en vivo usa el pipeline real (webhook→triaje→cert→gate de H2). Nada trucado.
- **Selector global:** una sola org activa compartida; el switcher en el topbar reemplaza los selectores locales de `calibration`/`defects`.
- **Sin dropdown shadcn** (no existe): usar un `<select>` nativo estilado (como `calibration/page.tsx` ya hace).
- Backend `python3 -m pytest -m "not integration"` (los tests del seed son `@pytest.mark.integration`, contra la BD prod, con cleanup vía la fixture `demo_user`); frontend `npm test` + `tsc` en `frontend/`.
- Commits terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Green baseline de `test_perfil` (self-heal en vivo)

**Files:** Create `scripts/demo_fixtures/perfil_green.json`; Modify `src/demo/seed.py`; Test `tests/test_demo_seed.py`.

**Interfaces:** Consumes — `seed_demo`, `_load_artifact` (existentes). Produces — un run verde de `checkout-suite/test_perfil` en Org A, de modo que ingerir `fresh_push.json` después dé categoría `maintenance` (R3).

- [ ] **Step 1: Create the fixture** `scripts/demo_fixtures/perfil_green.json` (clon de `maintenance_green.json` con `test_perfil` + el locator bueno `#guardar`):

```json
{"project": "checkout-suite", "org_id": "__ORG__", "commit_sha": "demo-perfil-baseline", "source": "playwright",
 "tests": [{"test_name": "test_perfil", "status": "pass",
            "dom": "<form id=\"perfil\"><button id=\"guardar\">Guardar</button></form>"}]}
```

(`fresh_push.json` ya existe con `test_perfil` `fail`, `locator not found: #guardar`, DOM `#guardar-cambios` → con este baseline verde: `has_green_baseline` + `dom_changed` → R3.)

- [ ] **Step 2: Seed it.** En `src/demo/seed.py`, añadir `"perfil_green.json"` al final de la tupla de runs de Org A:

```python
    for name in ("maintenance_green.json", "maintenance_red.json", "flaky.json", "real.json", "perfil_green.json"):
```

(Es un baseline verde independiente; va tras `real.json`. No tiene "red" en el seed — su red es `fresh_push` en vivo.)

- [ ] **Step 3: Write the failing test** — en `tests/test_demo_seed.py`, siguiendo el patrón del archivo (fixture `demo_user`, helpers de consulta a la BD, `@pytest.mark.integration`). El test siembra, ingiere `fresh_push` en Org A y verifica que el triaje lo marca `maintenance`. Lee primero cómo el archivo construye `seed_demo`/consulta categorías y reúsalo. Esquema:

```python
@pytest.mark.integration
def test_fresh_push_is_maintenance_with_baseline(demo_user):
    from src.demo.seed import seed_demo, _load_artifact
    from src.defects.repository import AssuranceRepository
    from src.defects.embedder import LocalEmbedder
    from src.ci.ingestion_service import CiIngestionService
    from src.triage.service import TriageService
    from src.config import DATABASE_URL

    res = seed_demo(db_url=DATABASE_URL, demo_user_id=demo_user)
    repo = AssuranceRepository(DATABASE_URL)
    ingest = CiIngestionService(repo=repo, embedder=LocalEmbedder())
    triage = TriageService(repo=repo)
    art = _load_artifact("fresh_push.json", res["org_a"])
    r = ingest.ingest_artifact(user_id=demo_user, artifact=art)
    triage.triage_run(user_id=demo_user, run_id=r["run_id"])
    # categoría del veredicto del run (reusar el helper de categorías del archivo)
    cats = _categories_for_run(r["run_id"])  # o la consulta inline que ya usa el test
    assert "maintenance" in cats
```

Si el archivo no tiene un helper de categoría por run, escribe la consulta inline (`select category from public.triage_verdicts where ...`) mirando cómo `test_seed_creates_two_orgs_with_processed_runs` consulta categorías.

- [ ] **Step 4: Run** — `python3 -m pytest tests/test_demo_seed.py -m integration -q`. Si tu entorno no tiene acceso a la BD prod para integración, al menos corre el resto y deja el test escrito; reporta el resultado real que obtengas. Verifica también que `python3 -m pytest -m "not integration" -q` sigue verde (el seed no rompe los unitarios).

- [ ] **Step 5: Commit**

```bash
git add scripts/demo_fixtures/perfil_green.json src/demo/seed.py tests/test_demo_seed.py
git commit -m "feat(demo): green baseline de test_perfil → el push en vivo da R3 maintenance (self-heal)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: Selector de organización global (aislamiento A/B)

**Files:** Create `frontend/src/components/providers/org-provider.tsx`, `frontend/src/components/layout/org-switcher.tsx`, `frontend/src/components/providers/__tests__/org-provider.test.tsx`; Modify `frontend/src/components/layout/app-shell.tsx` (o donde se monten los providers), `frontend/src/components/layout/topbar.tsx`, y las páginas `autopilot/page.tsx`, `assurance/page.tsx`, `defects/page.tsx`, `calibration/page.tsx`.

**Interfaces:** Produces — `OrgProvider`, `useActiveOrg(): { orgs: OrganizationResponse[]; activeOrgId: string; setActiveOrgId: (id: string) => void }`, `OrgSwitcher`.

- [ ] **Step 1: Create `OrgProvider` + `useActiveOrg`** (`frontend/src/components/providers/org-provider.tsx`) — mirror the `auth-provider.tsx` context pattern (`"use client"`, `createContext`, `useContext` hook). It loads orgs via `useQuery(getOrganizations)` using `useAuth().accessToken`, keeps `activeOrgId` in state (default = first org once loaded), persists the choice in `localStorage` (key `mnemo.activeOrgId`), and restores it on mount if still valid:

```tsx
"use client";

import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/providers/auth-provider";
import { getOrganizations } from "@/lib/api/endpoints";
import type { OrganizationResponse } from "@/lib/api/types";

interface OrgContextValue {
  orgs: OrganizationResponse[];
  activeOrgId: string;
  setActiveOrgId: (id: string) => void;
}
const OrgContext = createContext<OrgContextValue | null>(null);
const STORAGE_KEY = "mnemo.activeOrgId";

export function OrgProvider({ children }: PropsWithChildren) {
  const { accessToken } = useAuth();
  const [activeOrgId, setActive] = useState("");
  const orgsQuery = useQuery({
    queryKey: ["organizations"],
    queryFn: () => getOrganizations(accessToken!),
    enabled: Boolean(accessToken),
  });
  const orgs = orgsQuery.data ?? [];

  useEffect(() => {
    if (!orgs.length || activeOrgId) return;
    const stored = typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
    const valid = stored && orgs.some((o) => o.id === stored) ? stored : orgs[0].id;
    setActive(valid);
  }, [orgs, activeOrgId]);

  function setActiveOrgId(id: string) {
    setActive(id);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, id);
  }

  return <OrgContext.Provider value={{ orgs, activeOrgId, setActiveOrgId }}>{children}</OrgContext.Provider>;
}

export function useActiveOrg(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useActiveOrg must be used within OrgProvider");
  return ctx;
}
```

- [ ] **Step 2: Mount `OrgProvider`** in the authenticated tree. Read `frontend/src/components/layout/app-shell.tsx` and wrap its content with `<OrgProvider>` (inside the auth context, so `accessToken` is available). If `AppShell` already nests providers, add it there.

- [ ] **Step 3: Create `OrgSwitcher`** (`frontend/src/components/layout/org-switcher.tsx`) — a native `<select>` (styled like `calibration/page.tsx`'s) bound to `useActiveOrg`; if there's a single org, render its name as plain text (no select):

```tsx
"use client";
import { useActiveOrg } from "@/components/providers/org-provider";

export function OrgSwitcher() {
  const { orgs, activeOrgId, setActiveOrgId } = useActiveOrg();
  if (orgs.length === 0) return null;
  if (orgs.length === 1) return <span className="text-sm text-zinc-600">{orgs[0].name}</span>;
  return (
    <select
      aria-label="Organización"
      className="rounded-lg border border-zinc-200 px-2 py-1 text-sm"
      value={activeOrgId}
      onChange={(e) => setActiveOrgId(e.target.value)}
    >
      {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select>
  );
}
```

- [ ] **Step 4: Add `OrgSwitcher` to the `Topbar`** (`frontend/src/components/layout/topbar.tsx`) — render `<OrgSwitcher />` in the header's right side (near the existing user/signOut controls). Import it.

- [ ] **Step 5: Migrate the four pages** to the active org. In each, remove the local `getOrganizations`/`data?.[0]?.id` (and, in `calibration`/`defects`, their local org `<select>` + `orgId` state) and use `const { activeOrgId } = useActiveOrg();` as the org id passed downstream:
  - `autopilot/page.tsx`: `const orgId = orgsQuery.data?.[0]?.id ?? ""` → `const { activeOrgId: orgId } = useActiveOrg();` (drop its `orgsQuery`).
  - `assurance/page.tsx`: same (it uses `orgId` for `ingestReport`).
  - `calibration/page.tsx`: drop the local `<select>` + `orgId` state; `const { activeOrgId } = useActiveOrg();` feeds `getCalibrationMetrics`.
  - `defects/page.tsx`: drop the local org `<select>`/state; use `activeOrgId`.

- [ ] **Step 6: Write tests** (`frontend/src/components/providers/__tests__/org-provider.test.tsx`, vitest + jsdom, mirror `ActionsPanel.test.tsx`): mock `auth-provider` (`accessToken: "tok"`) + `getOrganizations` (two orgs). Assert: (a) a consumer of `useActiveOrg()` shows the first org's id by default; (b) calling `setActiveOrgId(secondId)` updates it and writes `localStorage["mnemo.activeOrgId"]`; (c) `OrgSwitcher` renders a `<select>` with both orgs and changing it switches the active org. Use a small test consumer component + `renderWithClient` (QueryClientProvider) wrapping `<OrgProvider>`.

- [ ] **Step 7: Run** — from `frontend/`: `npm test` → green (new + full suite); `tsc --noEmit` clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/providers/org-provider.tsx frontend/src/components/layout/org-switcher.tsx frontend/src/components/providers/__tests__/org-provider.test.tsx frontend/src/components/layout/app-shell.tsx frontend/src/components/layout/topbar.tsx frontend/src/app/app/autopilot/page.tsx frontend/src/app/app/assurance/page.tsx frontend/src/app/app/defects/page.tsx frontend/src/app/app/calibration/page.tsx
git commit -m "feat(ui): selector de organización global (aislamiento A/B en pantalla)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Guion + runbook de la demo

**Files:** Create `docs/demo/guion.md`, `docs/demo/runbook.md`.

- [ ] **Step 1: Write `docs/demo/guion.md`** — los 3 actos con, por acto: **qué se teclea**, **qué se ve**, **qué se dice** (1-2 frases de venta). Contenido real (no placeholders):
  - **Acto 1 — el problema (push→gate rojo):** se lanza el push en vivo (`fresh_push.json` al webhook `POST /v2/ci/webhook` con HMAC); el triaje automático marca `test_perfil` como **mantenimiento** (cambió el DOM: `#guardar`→`#guardar-cambios`); el gate del release queda **rojo** y el certificado **no-apto**. Mensaje: "un cambio de UI rompió el test; Mnemo lo detecta solo, sin intervención".
  - **Acto 2 — la acción (self-heal + aprobación):** Mnemo propone el parche del locator (`#guardar`→`#guardar-cambios`); el humano lo **aprueba** (Nivel 2, la IA nunca firma sola); se enseña el **certificado**, su **PDF** descargable (C3) y el **briefing** ejecutivo (C2). Mensaje: "determinismo donde firmo, IA donde multiplico".
  - **Acto 3 — aprendizaje + aislamiento (re-run→apto + foso + A/B):** re-run → gate **apto**; el panel de **calibración** (el "foso") muestra la precisión por cliente; con el **selector de organización** se pasa a **Org B "Cliente Beta"** → solo ve sus propios runs (**aislamiento multi-cliente**). Cierre con el **ROI** (C2: horas ahorradas, 0€/release). Mensaje: "cada cliente, su memoria; el motor mejora con cada corrección".
  - Incluir, al inicio, una tabla de tiempos aproximados por acto y la frase de apertura/cierre.

- [ ] **Step 2: Write `docs/demo/runbook.md`** — cómo dejar la demo lista y el plan B. Contenido real:
  - **Pre-requisitos:** variables de entorno necesarias (`DATABASE_URL`, `MNEMO_SIGNING_*`, `MNEMO_HMAC_*`/webhook secret, `ALLOW_EXTERNAL_LLM=false`), y que el LLM local (Ollama) esté arriba (o que el sistema degrada sin él).
  - **Levantar:** los comandos para arrancar el backend (`uvicorn asgi:app` / docker), el frontend (`npm run build && npm start` o `npm run dev` en `frontend/`), y **correr el seed** (`seed_demo` / el comando que lo dispara — `scripts/docker_init.py` lo invoca; documenta el camino real).
  - **El push en vivo:** el comando exacto para enviar `scripts/demo_fixtures/fresh_push.json` al webhook (curl con la firma HMAC, o el helper si existe), apuntando a Org A.
  - **Checklist pre-demo:** seed aplicado (Org A con 5 runs + Org B), el frontend abre en `/app/assurance`, login OK, el certificado de un run pre-sembrado descarga en PDF, el selector muestra las 2 orgs.
  - **Plan B:** si el push en vivo falla, los datos **pre-sembrados** de Org A (maintenance green→red de `test_login`) cubren el mismo discurso de los Actos 1-2; el Acto 3 (foso + A/B) no depende del push.

- [ ] **Step 3: Commit**

```bash
git add docs/demo/guion.md docs/demo/runbook.md
git commit -m "docs(demo): guion 3 actos + runbook de ensayo

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **T1 antes que nada** no es estricto, pero el guion (T3) referencia el self-heal de T1 y el selector de T2 — escribir T3 al final evita describir algo que cambió.
- **El selector reemplaza** los `<select>` locales de `calibration`/`defects` (no duplicar selectores): una sola org activa global.
- **Tests:** backend `-m integration` para el seed (BD prod, cleanup por fixture); frontend `npm test` + `tsc`.
- **Fuera de alcance:** Bloque D (pitch), grabar el vídeo, rediseño de UI más allá del switcher.
