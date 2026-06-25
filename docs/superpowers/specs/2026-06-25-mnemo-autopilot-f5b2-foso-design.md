# Mnemo Autopilot — F5b-2: Frontend del foso (métricas + etiquetado) (diseño)

**Fecha:** 2026-06-25 · **Fase:** F5b-2 (segunda del frontend de Autopilot) · **Rama:** `feat/mnemo-autopilot-foso` (apilada sobre `feat/mnemo-autopilot-ui`/PR #23; reapuntar a `main` cuando #23 mergee)

## Objetivo

Cerrar el lazo de aprendizaje **en la UI**: el humano **etiqueta** una familia de defectos (→ calibra el motor por cliente) y una pantalla de **métricas** muestra la **precisión del motor por cliente** (el diferenciador demostrable del foso). Reusa el patrón del frontend (Next.js 16, TanStack Query, proxy) y el api layer de F5b-1. Consume los endpoints de calibración de F5a (#22, contratos conocidos): `GET /v2/calibration/metrics?org_id=` y `PATCH /v2/defects/{family_id}/label`.

## Decisiones (confirmadas)

- **Métricas en una página nueva** `/app/calibration` con `accuracy` como número protagonista + desglose.
- **Etiquetado integrado en `/app/defects`** (columna de Linaje, junto a `RootCausePanel`) — no una vista nueva; es donde ya vive la familia.
- **Base apilada sobre #23** (reusa su patrón/api layer); reapunta a `main` al mergear #23. Consume calibración de #22 con contratos conocidos; **e2e requiere #22 y #23 en `main`** (los tests usan mocks, sin red).
- Solo consume vía HTTP (proxy + `Bearer`); UI en español; despliegue Vercel.

## Componentes

### API layer

- **`src/lib/api/types.ts` (añadir):** `CalibrationMetrics { total: number; aciertos: number; accuracy: number; familias_calibradas: number; por_categoria: Record<string, number> }`; `FamilyLabel { family_id: string; label: string }`.
- **`src/lib/api/endpoints.ts` (añadir):** `getCalibrationMetrics(token, orgId)` → `GET /api/v2/calibration/metrics?org_id=`; `setFamilyLabel(token, familyId, label, reason?)` → `PATCH /api/v2/defects/{familyId}/label` con body `{ label, reason }`.
- **Route handlers (`proxyToBackend`):** `src/app/api/v2/calibration/metrics/route.ts` (GET, forward `request.nextUrl.search`); `src/app/api/v2/defects/[family_id]/label/route.ts` (PATCH, forward el body con `contentType: "application/json"`).

### `src/app/app/calibration/page.tsx` (`"use client"`) — el foso
`useAuth` + `getOrganizations` → `orgId`; `useQuery getCalibrationMetrics(orgId)`. Render: una `Card` con la **`accuracy`** como número grande (p. ej. `{(accuracy*100).toFixed(0)}%` — "precisión del motor con tus correcciones"), y debajo `total` correcciones, `aciertos`, `familias_calibradas`, y el desglose `por_categoria` como Badges. Loading (Skeleton) / error / vacío (`total===0` → "Aún no hay correcciones; etiqueta familias en Defect DNA"). Si hay varias orgs, selector como en `defects/page.tsx`.

### `src/components/autopilot/FamilyLabelControl.tsx` — etiquetar (cierra el lazo)
`{ familyId: string; currentLabel?: string }`. `useAuth`; estado local `label` (select de `flaky/real/maintenance/infra/unknown`, inicializado a `currentLabel ?? "unknown"`) + `reason` (input opcional). Botón **"Etiquetar familia"** → `useMutation setFamilyLabel(token, familyId, label, reason)` → `toast` de éxito/error + invalida la query de linaje (`["lineage", familyId]`). Se renderiza en `defects/page.tsx` dentro de la columna de Linaje, junto a `RootCausePanel`, pasando `lineageQuery.data.family.id` (y `family.label` como `currentLabel` si el contrato lo trae).

### `src/components/layout/sidebar-nav.tsx`
Añadir el ítem "Calibración" (ruta `/app/calibration`, icono p. ej. `Gauge` de lucide-react).

## Manejo de errores

`ApiClientError` → `toast` (sonner) + mensaje en la Card. Auth vía `accessToken` (queries `enabled: Boolean(accessToken && orgId/familyId)`). Los route handlers forwardean `Authorization` y propagan el status del backend (incl. 404 si la familia/org no existe o no es miembro).

## Testing (Vitest + Testing Library, mocks; pragma `@vitest-environment jsdom` en los tests de componente)

- **`endpoints`:** `getCalibrationMetrics` → `/api/v2/calibration/metrics?org_id=...` (GET, Bearer); `setFamilyLabel` → `/api/v2/defects/{id}/label` (PATCH) con body `{label, reason}`.
- **`CalibrationPage` / sección de métricas:** render con datos mock pinta `accuracy`, `familias_calibradas` y el desglose; estado vacío (`total===0`).
- **`FamilyLabelControl`:** seleccionar una categoría + click "Etiquetar familia" dispara `setFamilyLabel` con `(token, familyId, label, reason)` correctos.

## Fases (tareas del plan)

1. **API layer:** tipos + `getCalibrationMetrics`/`setFamilyLabel` + 2 route handlers + tests de endpoints.
2. **Página del foso:** `/app/calibration` (métricas) + ítem de nav + tests.
3. **Etiquetado:** `FamilyLabelControl` + integración en `defects/page.tsx` + tests.

## Fuera de alcance (YAGNI / fases posteriores)

- **Bandeja global** de acciones pendientes (todas, no por run) = **F5b-3** (la aprobación ya está inline en F5b-1).
- Historial de correcciones (`triage_corrections` detallado); gráficas de tendencia de la precisión; HTML imprimible del cert. **F6** (demo).
