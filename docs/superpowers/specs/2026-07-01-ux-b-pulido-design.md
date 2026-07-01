# UX · Sub-proyecto B — Pulido transversal — diseño

**Fecha:** 2026-07-01 · **Parte de:** mejora UX A→B→C (auditoría `docs/auditoria/2026-06-28-completa/04-frontend-ux.md`) · **Base:** `main` a9393b1 (con UX-A #54 + pool #58) · **Frontend:** Next.js/TS/shadcn+Radix.

## Objetivo

Subir la calidad percibida y la claridad de la app sin tocar la lógica de negocio: cargar la tipografía real, explicar la jerga, unificar los estados de carga, confirmar las acciones que mutan, unificar los selects y mejorar la accesibilidad. Recoge los hallazgos sistémicos S2–S10 y el TOP 10 de la auditoría que no cubrió A (orientación/nav) ni cubrirá C (empaquetado).

## Decisiones (confirmadas)

- **Primitivos nuevos estilo shadcn** en `frontend/src/components/ui/`, sobre **Radix** (el proyecto ya usa `@radix-ui/react-{label,separator,slot,tabs}` + `cva` + `cn`): añadir `@radix-ui/react-tooltip`, `@radix-ui/react-select`, `@radix-ui/react-alert-dialog`.
- **Glosario de jerga** como un mapa `término → definición` (`frontend/src/lib/glossary.ts`) reutilizado por `<InfoTooltip>`.
- **Confirmar solo lo que MUTA de forma consecuente**: Aprobar/Rechazar en `ActionsPanel` (crean PR/ticket/self-heal reales). "Analizar causa raíz" → aviso de coste/latencia (no bloqueante).
- **Fuentes** con `next/font/google` (Manrope + JetBrains Mono) enlazadas a las variables CSS ya declaradas.
- **Un solo sub-proyecto** con un plan de varias tareas (no dividir en B1/B2): las piezas comparten los primitivos nuevos.
- **No romper funcionalidad**: solo UI/UX, textos, a11y y wrappers de confirmación; las mutaciones y queries no cambian.

## Componentes / áreas (el plan las descompone en tareas)

### 1. Tipografía + minors de UX-A (pulido base)
- `layout.tsx`: `next/font/google` para **Manrope** (sans) y **JetBrains Mono** (mono), exponiendo sus variables y enganchándolas a `--font-sans`/`--font-mono` de `globals.css`.
- Los 3 minors del review de A: quitar el subtítulo redundante "Mnemo" del topbar; el empty-state de onboarding (caso sin-org) enlaza a `/app/org` (no `/app/knowledge`); el quick-access del dashboard deriva de `NAV_ITEMS`.

### 2. Primitivos nuevos + glosario
- `ui/tooltip.tsx` (Radix Tooltip) + `ui/InfoTooltip.tsx` (icono `?` de lucide + `aria-label`, recibe un `term` o `content`).
- `ui/select.tsx` (Radix Select, estilo shadcn) — API mínima usada por los 3 call-sites.
- `ui/alert-dialog.tsx` (Radix AlertDialog, estilo shadcn) — con acción/cancelación.
- `lib/glossary.ts`: `GLOSSARY: Record<string,string>` con los términos de dominio (foso, briefing, gate, "Nivel 2"/acciones propuestas, regla_sin_test, defecto_sin_conocimiento, Defect DNA, triaje, certificado firmado, risk score, calibración…). `<InfoTooltip term="foso" />` busca en el glosario.

### 3. Jerga aplicada + traducción de valores crudos
- Colocar `<InfoTooltip>` junto a los términos en los sitios que lista la auditoría (TriageVerdictList, ActionsPanel, calibration, graph, defects, CertificateCard, GateCard…). Leyenda de color donde hay color-coding (categorías de triaje, severidades de gap).
- Mapear los `kind`/valores crudos a etiquetas humanas: acciones (`quarantine`→"Cuarentena", `ticket`→"Ticket", `self_heal`→"Auto-reparación"), categorías de triaje, severidades.

### 4. Estados de carga
- Estandarizar en `<Skeleton>` (ya existe) los "Cargando…" de texto plano: `onboarding`, `knowledge`, `integrations`, `BriefingCard`.

### 5. Confirmaciones + Select
- `ActionsPanel`: envolver Aprobar/Rechazar en `<AlertDialog>` con el efecto explícito ("Esto creará un PR en owner/repo" / "abrirá un ticket" / "aplicará un self-heal"). "Analizar causa raíz": aviso de coste/latencia (texto/tooltip; no un dialog bloqueante).
- Reemplazar los `<select>` crudos por `<Select>`: `org-switcher.tsx`, `knowledge` (Tipo), `FamilyLabelControl`.

### 6. Accesibilidad + Integrations
- Grafo (`knowledge-graph-view.tsx`): `aria-label` descriptivo + región `aria-live` que anuncie el nodo seleccionado; el panel de gaps como lista semántica; severidades con icono+texto (no solo color).
- `integrations/page.tsx`: reordenar (config GitHub primero, luego indexar), badge "✓ Conectado" tras guardar, help-text de formato en Installation ID / owner-repo.

## Garantías
- **No rompe negocio**: las mutaciones (Aprobar/Rechazar/PR/ticket/self-heal, indexar) siguen igual; solo se envuelven en confirmación y se re-etiquetan. Queries intactas.
- **Reusa**: Radix + cva + `cn` (patrón de los primitivos existentes), `Skeleton`, `NAV_ITEMS`.
- **A11y**: los primitivos Radix aportan roles/foco/teclado correctos; se añaden `aria-label`/`aria-live` donde faltan.

## Testing (vitest)
- Cada primitivo: `InfoTooltip` (muestra el contenido del glosario / aria-label), `Select` (cambia valor), `AlertDialog` (confirma → ejecuta; cancela → no).
- Confirmaciones: al pulsar Aprobar aparece el diálogo; la mutación solo corre tras confirmar.
- Skeletons: las 4 páginas muestran `<Skeleton>` en carga (no texto plano).
- a11y: el grafo tiene `aria-label`; las severidades tienen texto además de color.
- Minors de A y fuentes: el topbar sin subtítulo redundante; onboarding sin-org → link `/app/org`.
- **Verificación local = CI** por tarea: `npm run lint:ci` + `test` + `tsc` + `build` (`npm --prefix frontend ci` si node_modules se corrompe por iCloud).

## Fuera de alcance
- A (dashboard/nav/idioma — hecho) y C (verify público, recorrido del lazo, demo/seed, docs).
- `surface.tsx` roto (S9) e i18n completo — follow-ups menores, no en B salvo que caigan de paso.
- Rediseño visual mayor: B pule el sistema actual, no lo reemplaza.
