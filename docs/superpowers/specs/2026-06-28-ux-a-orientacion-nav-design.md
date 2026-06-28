# UX · Sub-proyecto A — Orientación + Navegación — diseño

**Fecha:** 2026-06-28 · **Parte de:** mejora UX+empaquetado (auditoría `docs/auditoria/2026-06-28-completa/`, lente 04-frontend-ux) · **Base:** `main` 2ade121 · **Frontend:** Next.js/TS/shadcn.

## Objetivo

Dar al usuario un **punto de partida y un mapa**. Hoy `/app` redirige a `assurance` (una página que exige un report que el usuario nuevo no tiene) y el sidebar son 11 ítems planos en EN/ES mezclado. A resuelve la barrera #1 de intuitividad de la auditoría (S1, S5, S6, S8) sin tocar la lógica de negocio.

## Decisiones (confirmadas)

- **Identidad:** el producto se llama **Mnemo** (descriptor: "continuidad de QA"). Unificar el footer (hoy "QA Autopilot") y los textos de marca a "Mnemo".
- **Idioma:** UI en **español**; se mantienen los nombres de marca de feature (Assurance, Autopilot, Defect DNA, Knowledge Graph, Onboarding). `lang="es"`.
- **Alcance de A:** dashboard + sidebar agrupado + idioma/identidad + empty-states de las páginas del lazo. Tooltips de jerga, fuentes, skeletons globales, confirmaciones y `Select` = **sub-proyecto B**.

## Componentes

### 1. Dashboard `/app` (`frontend/src/app/app/page.tsx`, reemplaza el `redirect`)
Página cliente que orienta. Reusa `useActiveOrg`, `useAuth`, `useQuery` y los clientes existentes.
- **Checklist "Pon Mnemo en marcha"** — un componente `SetupChecklist` con 5 pasos; cada paso: estado (✓ hecho / ○ pendiente), título, una línea de descripción, y un botón-CTA (`<Link>`) al sitio correcto:
  1. **Conecta GitHub** → `/app/integrations` — hecho si `getGithubConfig({org_id}).configured`.
  2. **Indexa los tests de tu repo** → `/app/integrations` — hecho si `listRepoTests({org_id}).length > 0`.
  3. **Captura conocimiento de QA** → `/app/knowledge` — hecho si `listKnowledge(orgId).length > 0`.
  4. **Revisa tus gaps de cobertura** → `/app/graph` — hecho si `getGaps({org_id}).length > 0`.
  5. **Genera el test que falta** → `/app/graph` — CTA destacado (el lazo ★); sin estado persistente, siempre disponible.
- **Estados**: mientras cargan las queries → `<Skeleton>` con la forma de la lista (no texto plano). Si `!activeOrgId` → empty-state "Crea o únete a una organización" con CTA a `/app/org`. Errores de query → mensaje con reintento (no romper la página).
- **Accesos rápidos**: bajo el checklist, una fila de cards-enlace a las 3 áreas (Conocimiento, Grafo, Plan de pruebas) para el usuario ya configurado.
- El checklist deriva su estado de queries independientes; un paso cuya query falla se muestra como "pendiente" (no bloquea el resto).

### 2. Sidebar agrupado (`frontend/src/components/layout/sidebar-nav.tsx`)
Reestructurar `navItems` (hoy un array plano) en **secciones** y renderizar cada una con un encabezado (`text-xs font-medium uppercase tracking-wide text-zinc-400 px-3`):
```ts
const navSections = [
  { title: null,            items: [{ href: "/app", label: "Dashboard", icon: LayoutDashboard }] },
  { title: "Continuidad",   items: [Conocimiento, Onboarding, "Knowledge Graph", "Plan de pruebas"] },
  { title: "Aseguramiento", items: ["Assurance", "Autopilot", "Defect DNA", "Calibración"] },
  { title: "Configuración", items: ["Integraciones", "Organización", "Ajustes"] },
];
```
Labels finales: Dashboard · Conocimiento · Onboarding · Knowledge Graph · Plan de pruebas · Assurance · Autopilot · Defect DNA · Calibración · **Integraciones** (era "Integrations") · **Organización** (era "Organization") · **Ajustes** (era "Settings"). El logo enlaza a `/app` (dashboard) en vez de `/`. Footer: "Mnemo · continuidad de QA · privado · on-premise". El `active` se mantiene por `pathname === href` (con cuidado: `/app` exacto, no prefijo, para no marcarlo siempre activo).

### 3. Idioma / identidad
- `frontend/src/app/layout.tsx:18` → `<html lang="es">`.
- **Topbar** (`frontend/src/components/layout/topbar.tsx`): derivar el título de una **fuente única** — exportar un mapa `href → label` desde `sidebar-nav.tsx` (o un módulo `nav.ts` compartido) y usarlo en el topbar (hoy `pageTitles` cubre solo 6 rutas → 5 páginas muestran "Mnemo"). Quitar el subtítulo fijo jergoso ("Triaje determinista · …") o dejar uno neutro.
- "Sign out" → "Cerrar sesión".

### 4. Empty-states con CTA (solo las páginas del lazo)
Donde hoy hay un vacío sin salida, añadir mensaje + `<Link>` al siguiente paso:
- `graph/page.tsx` (~163) "Aún no hay conocimiento suficiente" → enlace a `/app/knowledge`.
- `calibration/page.tsx` (~36) → enlace a `/app/defects`.
- `onboarding/page.tsx` (resumen vacío) → enlace a `/app/knowledge`.

## Garantías
- **No rompe lógica**: solo navegación, una página nueva y textos. Las queries del dashboard son de solo lectura y degradan (paso "pendiente" si fallan).
- **Reusa**: shadcn (Card/Button/Skeleton), los clientes existentes, `useActiveOrg`/`useAuth`.
- **Accesibilidad**: el checklist como `<ol>`; los pasos con estado textual además del icono.

## Testing (vitest)
- `SetupChecklist`: con queries mockeadas → marca ✓ los pasos cuyo dato existe y ○ los demás; cada CTA enlaza al href correcto; sin org → empty-state con CTA a `/app/org`; estado de carga → skeleton.
- `SidebarNav`: renderiza los 4 grupos con sus encabezados; los 12 enlaces (incl. Dashboard) con los labels ES; resalta el activo; el de `/app` no queda activo en otras rutas.
- `Topbar`: el título sale de la fuente única para una ruta que antes caía a "Mnemo" (p.ej. `/app/integrations` → "Integraciones").
- Gate CI: `npm run lint:ci` + `test` + `tsc` + `build` (y `npm --prefix frontend ci` si node_modules se corrompe por iCloud).

## Fuera de alcance (otros sub-proyectos)
- B: fuentes, `<InfoTooltip>`+jerga, skeletons en todas las páginas, confirmaciones destructivas, primitivo `Select`, a11y del grafo, reordenar Integrations.
- C: verify público + página pública, recorrido guiado del lazo, demo/seed con las capacidades, sincronizar docs.
