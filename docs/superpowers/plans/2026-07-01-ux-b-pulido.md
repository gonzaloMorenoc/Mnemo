# UX · Sub-proyecto B (Pulido transversal) — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir calidad percibida y claridad (tipografía, jerga explicada, estados de carga, confirmaciones, selects unificados, a11y) sin tocar la lógica de negocio.

**Architecture:** T1 tipografía + minors de A. T2 crea los primitivos Radix (tooltip/select/alert-dialog) + glosario. T3–T6 los aplican (jerga, skeletons, confirmaciones/select, a11y/integrations).

**Tech Stack:** Next.js (App Router) · TypeScript · shadcn+Radix · TanStack Query · vitest.

## Global Constraints

- **Primitivos nuevos = patrón shadcn del proyecto** (`ui/tabs.tsx`/`ui/button.tsx`): `import * as X from "@radix-ui/react-x"`, wrappers con `cn(...)`, estética zinc + `rounded-xl`.
- **No romper negocio**: las mutaciones (approve/reject/propose/index) y queries NO cambian; solo se envuelven en confirmación, se re-etiquetan valores crudos, se añaden tooltips/skeletons/aria.
- **Confirmar solo lo que muta de forma consecuente**: Aprobar/Rechazar (PR/ticket/self-heal). "Analizar causa raíz" → aviso no bloqueante (texto/tooltip).
- **Verificación local = CI por tarea:** `npm run lint:ci` + `npm test` + `npx tsc --noEmit` + `npm run build` (desde `frontend/`). Si node_modules se corrompe (iCloud) → `npm --prefix frontend ci`. **No git worktree.** Commits con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Tipografía (next/font) + 3 minors de UX-A

**Files:** Modify `frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`, `frontend/src/components/layout/topbar.tsx`, `frontend/src/app/app/onboarding/page.tsx`, `frontend/src/app/app/page.tsx`.

- [ ] **Step 1: Fonts** — en `layout.tsx`:
```tsx
import { Manrope, JetBrains_Mono } from "next/font/google";
const sans = Manrope({ subsets: ["latin"], variable: "--font-sans-loaded", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono-loaded", display: "swap" });
// en <html className={`${sans.variable} ${mono.variable}`} lang="es">
```
En `globals.css`, hacer que `--font-sans`/`--font-mono` usen las variables cargadas con fallback: `--font-sans: var(--font-sans-loaded), "Manrope", "Segoe UI", sans-serif;` y `--font-mono: var(--font-mono-loaded), "JetBrains Mono", monospace;`.

- [ ] **Step 2: Minor A1 (topbar)** — en `topbar.tsx`, eliminar el `<p>` de subtítulo que muestra "Mnemo" (redundante con el título). Dejar solo el `<h1>` del título.

- [ ] **Step 3: Minor A2 (onboarding empty-state)** — en `onboarding/page.tsx` (~línea 72–90, el bloque `!activeOrgId`): el CTA debe enlazar a `/app/org` ("Ir a Organización"), no a `/app/knowledge` (es el caso sin organización).

- [ ] **Step 4: Minor A3 (dashboard quick-access)** — en `app/app/page.tsx`, la fila de accesos rápidos deriva de `NAV_ITEMS` (importar de `@/components/layout/nav`), filtrando a Conocimiento/Knowledge Graph/Plan de pruebas por href, en vez del array literal.

- [ ] **Step 5: Test + gate** — test vitest: el topbar ya no renderiza el subtítulo "Mnemo" duplicado; onboarding sin-org enlaza a `/app/org`. Run `lint:ci`+`test`+`tsc`+`build`. **Commit** `feat(ux): tipografía real (next/font) + minors de UX-A` + trailer.

---

## Task 2: Primitivos (tooltip/select/alert-dialog) + glosario

**Files:** Modify `frontend/package.json` (deps); Create `frontend/src/components/ui/tooltip.tsx`, `frontend/src/components/ui/InfoTooltip.tsx`, `frontend/src/components/ui/select.tsx`, `frontend/src/components/ui/alert-dialog.tsx`, `frontend/src/lib/glossary.ts`; Tests under `frontend/src/components/ui/__tests__/`.

**Interfaces (Produces):** `<InfoTooltip term?|content?>`, `<Select value onValueChange>` (+ `SelectItem`), `<AlertDialog>`/`AlertDialogTrigger`/`AlertDialogContent`/`AlertDialogAction`/`AlertDialogCancel`, `GLOSSARY`.

- [ ] **Step 1: Deps** — `npm --prefix frontend install @radix-ui/react-tooltip @radix-ui/react-select @radix-ui/react-alert-dialog`.

- [ ] **Step 2: Glosario** (`src/lib/glossary.ts`):
```ts
export const GLOSSARY: Record<string, string> = {
  foso: "El foso: tus correcciones acumuladas que calibran el motor de triaje.",
  briefing: "Resumen ejecutivo del run: veredicto, recomendación y riesgo.",
  gate: "Estado publicado como check de GitHub (listo para merge / bloqueado).",
  "regla_sin_test": "Una regla/flujo/riesgo de QA sin un test que lo cubra.",
  "defecto_sin_conocimiento": "Un defecto recurrente sin una lección capturada.",
  triaje: "Clasificación automática de un fallo (real, flaky, mantenimiento, infra).",
  certificado: "Certificado de aseguramiento firmado: prueba verificable del run.",
  "risk_score": "Puntuación de riesgo del run (mayor = más atención).",
  calibracion: "Ajuste del motor con tus etiquetas de verdad de referencia.",
  self_heal: "Auto-reparación: PR propuesto que arregla un locator/selector roto.",
};
```

- [ ] **Step 3: tooltip + InfoTooltip** (`ui/tooltip.tsx` Radix wrappers + `ui/InfoTooltip.tsx`):
```tsx
// InfoTooltip.tsx
import { HelpCircle } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { GLOSSARY } from "@/lib/glossary";
export function InfoTooltip({ term, content, label }: { term?: string; content?: string; label?: string }) {
  const text = content ?? (term ? GLOSSARY[term] : "") ?? "";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" aria-label={label ?? `Qué es: ${term ?? "ayuda"}`}
          className="inline-flex text-zinc-400 hover:text-zinc-600 align-middle">
          <HelpCircle size={14} />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">{text}</TooltipContent>
    </Tooltip>
  );
}
```
`ui/tooltip.tsx`: `Tooltip = TooltipPrimitive.Root` (envuelto en `TooltipPrimitive.Provider`), `TooltipTrigger`, `TooltipContent` con `cn("rounded-lg bg-zinc-900 text-white px-2 py-1 shadow", className)`. Sigue el patrón de `tabs.tsx`.

- [ ] **Step 4: select.tsx** (Radix Select estilo shadcn): `Select`, `SelectTrigger`, `SelectValue`, `SelectContent`, `SelectItem` con `cn(...)` (rounded-xl, zinc, focus ring como `input.tsx`).

- [ ] **Step 5: alert-dialog.tsx** (Radix AlertDialog): `AlertDialog`, `AlertDialogTrigger`, `AlertDialogContent` (con overlay), `AlertDialogTitle`, `AlertDialogDescription`, `AlertDialogAction`, `AlertDialogCancel` con `cn(...)`.

- [ ] **Step 6: Tests** (vitest, `ui/__tests__/`): `InfoTooltip` renderiza el botón con `aria-label` y expone el texto del glosario para un `term`; `Select` cambia el valor con `onValueChange`; `AlertDialog` — al confirmar dispara `onClick` de la acción, al cancelar no. (Usar `@testing-library/react`; Radix necesita interacción real — `userEvent`.)

- [ ] **Step 7: Gate + commit** `lint:ci`+`test`+`tsc`+`build`. **Commit** `feat(ui): primitivos tooltip/select/alert-dialog + glosario` + trailer.

---

## Task 3: Jerga aplicada + traducción de valores crudos

**Files:** Modify `frontend/src/components/autopilot/{TriageVerdictList,ActionsPanel,CertificateCard,GateCard}.tsx`, `frontend/src/app/app/{calibration,graph,defects}/page.tsx`. Test: uno de ellos.

- [ ] **Step 1** — Añadir `<InfoTooltip term="…">` junto a los títulos/labels de dominio en cada sitio que la auditoría lista (reconfirmar líneas): "foso" (calibration/graph), "Acciones (Nivel 2)"/"triaje" (ActionsPanel/TriageVerdictList), "Defect DNA"/"linaje" (defects), "certificado"/"risk score" (CertificateCard), "Gate" (GateCard), gap kinds (graph).
- [ ] **Step 2** — Mapas de etiquetas humanas para valores crudos: en `ActionsPanel` `a.kind` (`quarantine`→"Cuarentena", `ticket`→"Ticket", `self_heal`→"Auto-reparación"); en `TriageVerdictList` la categoría; leyenda de color inline donde hay color-coding (categorías de triaje, severidades). Usar un `Record<string,string>` local por componente o en `glossary.ts` si se comparte.
- [ ] **Step 3: Test** — un componente (p.ej. `ActionsPanel`) muestra la etiqueta humana del `kind` (no el valor crudo) y un `InfoTooltip` con `aria-label`. Gate + **Commit** `feat(ux): tooltips de jerga + etiquetas humanas` + trailer.

---

## Task 4: Estados de carga → Skeleton

**Files:** Modify `frontend/src/app/app/{graph,integrations,knowledge,onboarding,test-plan}/page.tsx`, `frontend/src/components/autopilot/BriefingCard.tsx`. Test: uno.

- [ ] **Step 1** — Reemplazar cada `<p ...>Cargando…</p>` (graph:134,195 · integrations:211 · knowledge:113 · onboarding:72 · test-plan:294 · BriefingCard:37) por un `<Skeleton>` (de `@/components/ui/skeleton`) con la forma aproximada del contenido (p.ej. `<Skeleton className="h-24 w-full rounded-xl" />` o varias líneas). No cambiar la condición que dispara la carga.
- [ ] **Step 2: Test** — una página muestra un `Skeleton` (por `data-testid` o rol) en estado de carga en vez del texto. Gate + **Commit** `feat(ux): skeletons consistentes en la carga` + trailer.

---

## Task 5: Confirmaciones (AlertDialog) + Select

**Files:** Modify `frontend/src/components/autopilot/ActionsPanel.tsx`, `frontend/src/app/app/defects/page.tsx` (RootCausePanel), `frontend/src/components/layout/org-switcher.tsx`, `frontend/src/app/app/knowledge/page.tsx`, `frontend/src/components/autopilot/FamilyLabelControl.tsx`, `frontend/src/app/app/assurance/page.tsx`. Tests: ActionsPanel + un select.

- [ ] **Step 1: Confirmaciones** — en `ActionsPanel.tsx`, los botones Aprobar (línea 60) y Rechazar (61) que hoy hacen `approve.mutate(a.id)` / `reject.mutate(a.id)` directo → envolver en `<AlertDialog>`: el trigger es el botón, el `AlertDialogContent` describe el efecto según `a.kind` ("Esto creará un PR…" / "abrirá un ticket…" / "aplicará una auto-reparación…"), `AlertDialogAction` ejecuta `approve.mutate(a.id)`, `AlertDialogCancel` no hace nada. La mutación NO cambia.
- [ ] **Step 2: Aviso causa raíz** — en `defects/page.tsx` RootCausePanel, junto a "Analizar causa raíz", un `<InfoTooltip content="Usa el LLM; puede tardar unos segundos." />` o texto de ayuda (NO un dialog bloqueante).
- [ ] **Step 3: Select** — reemplazar los `<select>` crudos por `<Select>`: `org-switcher.tsx:9`, `knowledge/page.tsx:155` (Tipo), `FamilyLabelControl.tsx:35`, `assurance/page.tsx:72`. Preservar los `value`/`onChange` (ahora `onValueChange`) y las opciones.
- [ ] **Step 4: Tests** — `ActionsPanel`: pulsar Aprobar abre el diálogo; `approve.mutate` solo se llama tras confirmar (mock). Un select: cambiar el valor invoca el handler. Gate + **Commit** `feat(ux): confirmación en acciones que mutan + Select unificado` + trailer.

---

## Task 6: Accesibilidad del grafo + Integrations

**Files:** Modify `frontend/src/components/graph/knowledge-graph-view.tsx`, `frontend/src/app/app/graph/page.tsx`, `frontend/src/app/app/integrations/page.tsx`. Tests.

- [ ] **Step 1: a11y grafo** — en `knowledge-graph-view.tsx`, el contenedor del grafo con `role="application"` + `aria-label="Grafo de conocimiento"`; una región `aria-live="polite"` (visualmente oculta o pequeña) que anuncie el nodo seleccionado. En `graph/page.tsx`, el panel de gaps como `<ul aria-label="Gaps de cobertura">`/`<li>`; la severidad con **icono + texto** (no solo color) — p.ej. un icono por nivel + el texto "alta/media/baja".
- [ ] **Step 2: Integrations** — en `integrations/page.tsx`, reordenar para que la config de GitHub aparezca antes que "Indexar tests del repo" (o deshabilitar/ocultar el indexado hasta que GitHub esté configurado); badge "✓ Conectado" cuando `githubConfig.configured`; help-text de formato en Installation ID (numérico) y owner/repo (`owner/nombre`).
- [ ] **Step 3: Tests** — el grafo expone `aria-label`; una severidad muestra su texto además del color; Integrations muestra el badge Conectado cuando configurado. Gate + **Commit** `feat(ux): a11y del grafo + orden y estado de Integrations` + trailer.

---

## Notas de cierre
- **Orden:** T1 (base) → T2 (primitivos) → T3/T4/T5/T6 (aplicación; T3/T5/T6 dependen de los primitivos de T2). T4 (skeletons) es independiente de T2.
- **Reusa:** el patrón shadcn/Radix (`tabs.tsx`/`button.tsx`), `Skeleton`, `NAV_ITEMS`, `cn`.
- **No rompe negocio:** las mutaciones/queries no cambian; solo wrappers de confirmación, textos, tooltips, skeletons y aria. Reconfirmar los números de línea de la auditoría al implementar (algunos son ~aprox).
- **Fuera de alcance:** A (hecho) y C (verify público, recorrido del lazo, demo/seed, docs); `surface.tsx` roto e i18n completo.
