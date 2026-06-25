# Mnemo Autopilot — F5b-1: Frontend, vista del run (diseño)

**Fecha:** 2026-06-25 · **Fase:** F5b-1 (primera del frontend de Autopilot) · **Rama:** `feat/mnemo-autopilot-ui` (desde `main`)

## Objetivo

La **cara de la demo de 3 actos**: una página `/app/autopilot` que, para un run, recorre el flujo completo en una pantalla — **triaje** (veredictos categorizados) → **acción Nivel 2** (proponer + aprobar/rechazar, con el artefacto real de GitHub) → **certificado** firmado → **gate** (rojo/verde). Consume endpoints que **ya están en `main`** (triage/actions/certificates/gate); no depende de F5a (calibración, que es F5b-2). Replica el patrón del frontend existente (Next.js 16 App Router, TanStack Query, Supabase auth, proxy).

## Decisiones (confirmadas)

- **Una página, secciones apiladas** (patrón de `assurance/page.tsx`): el flujo se revela según avanza (run → veredictos → acciones → certificado → gate).
- **Componentes pequeños y enfocados** en `components/autopilot/`: `RunSelector`, `TriageVerdictList`, `ActionsPanel`, `CertificateCard`, `GateCard`.
- **Certificado: render del JSON nativo** (no iframe del HTML — el endpoint `/html` requiere `Bearer` que un `<iframe src>` no envía). El HTML imprimible es follow-up.
- **Acciones: approve/reject inline** en la vista del run. La **bandeja global** y el **foso** (métricas + etiquetado) son **F5b-2**.
- **Selección de run** por upload de reporte (reusa `ingestReport`) o input manual de `run_id` (no hay endpoint de lista de runs).
- **Solo consume vía HTTP** (proxy + `Bearer`); tests con mocks (sin red). Despliegue Vercel (cliente; backend on-premise).

## Componentes

### Página `src/app/app/autopilot/page.tsx` (`"use client"`)
Orquesta el estado `runId` (string | null) y `orgId` (de `getOrganizations`, patrón de `assurance`). Renderiza las cinco secciones en `Card`s; cada sección se habilita cuando hay `runId`. Sin lógica de negocio propia más allá de coordinar `runId`.

### `components/autopilot/RunSelector.tsx`
Form de upload (proyecto + formato + archivo, como `assurance`) → `ingestReport` → `onRunId(run_id)`. Más un input de texto "o pega un run_id" → `onRunId`. Estados submitting/error.

### `components/autopilot/TriageVerdictList.tsx`
`useQuery` `getTriageVerdicts(token, runId)` → lista de veredictos. Por veredicto: nombre/`failure_id`, `Badge` de color por `category` (real=rojo, flaky=ámbar, maintenance=azul, infra=gris, unknown=zinc), `confidence`, `rule_applied`, marca "requiere aprobación" si `requires_approval`. Loading (Skeleton) / error / vacío.

### `components/autopilot/ActionsPanel.tsx`
Botón "Proponer acciones" → `proposeActions(token, runId)` (mutation) → invalida la query de acciones. `useQuery` `getActions(token, runId)` (filtrado por `run_id`; client-side si el endpoint no lo soporta). Por acción: `kind`, `summary`, `status` (`Badge`), y si `proposed` → botones **Aprobar** / **Rechazar** (mutations `approveAction`/`rejectAction`, con campo de motivo opcional para rechazar); si `materialized` → enlace al `artifact_ref` (Issue/PR de GitHub). Invalidación tras cada mutation; errores → `toast`.

### `components/autopilot/CertificateCard.tsx`
Botón "Generar certificado" → `generateCertificate(token, runId)` (mutation). `useQuery` `getCertificate(token, runId)` → render nativo del `canonical_json`: veredicto (`Badge`), `risk_score`, desglose por categoría, lista de evidencia, firma (truncada). Estados loading/error/sin-certificado.

### `components/autopilot/GateCard.tsx`
Botón "Publicar gate" → `publishGate(token, runId)` (mutation) → muestra `conclusion` con `Badge` (🟢 success / ⚪ neutral / 🔴 failure) + `verdict` + enlace `check_run_url`. Sin persistencia (el resultado es el de la última publicación).

### `components/layout/sidebar-nav.tsx`
Añadir el ítem "Autopilot" (ruta `/app/autopilot`) al array `navItems`.

## API layer

### `src/lib/api/types.ts` (añadir)
`TriageVerdict` (`id, failure_id, category, confidence, rule_applied, requires_approval, llm_assisted, status`), `ActionItem` (`id, run_id, kind, summary, status, artifact_ref`), `ProposeActionsResult`, `ActionMutationResult`, `Certificate` (`run_id, verdict, risk_score, canonical_json, signature, created_at`), `GateResult` (`verdict, conclusion, check_run_url`). Formas derivadas de los `response_model` del backend (verificar campos exactos en `src/multitenant_models.py` al planificar).

### `src/lib/api/endpoints.ts` (añadir, patrón `apiRequest<T>`)
`getTriageVerdicts(token, runId)`, `proposeActions(token, runId)`, `getActions(token, runId?)`, `approveAction(token, actionId)`, `rejectAction(token, actionId, reason?)`, `generateCertificate(token, runId)`, `getCertificate(token, runId)`, `publishGate(token, runId)`.

### Route handlers proxy (`src/app/api/v2/...`, patrón `proxyToBackend`)
`triage/run/[run_id]` (GET); `actions` (GET); `actions/run/[run_id]/propose` (POST); `actions/[action_id]/approve` (POST); `actions/[action_id]/reject` (POST); `certificates/run/[run_id]` (POST); `certificates/[run_id]` (GET); `gate/run/[run_id]` (POST).

## Manejo de errores

`ApiClientError` (del `apiRequest`) → `toast` (sonner) + mensaje en la Card. Auth vía `accessToken` (si falta, las queries quedan `enabled:false`). Los route handlers forwardean el `Authorization` y propagan el status del backend.

## Testing (Vitest + Testing Library, mocks)

- **Componentes:** cada uno renderiza con datos mock (mock de las funciones de `endpoints.ts`): `TriageVerdictList` pinta categorías/badges; `ActionsPanel` muestra approve/reject solo en `proposed` y dispara la mutation correcta; `CertificateCard` pinta el veredicto/risk; `GateCard` pinta la conclusion; estados loading/error/vacío.
- **`endpoints.ts`:** cada función llama a la ruta `/api/v2/...` correcta con el método correcto (mock de `apiRequest`/`fetch`).
- Sin red real ni backend.

## Fases (tareas del plan)

1. **API layer:** tipos + funciones de `endpoints.ts` + route handlers proxy + tests de `endpoints`.
2. **Lectura:** página `/app/autopilot` (orquesta `runId`) + `RunSelector` + `TriageVerdictList` + ítem de nav + tests.
3. **Acción:** `ActionsPanel` (propose + approve/reject) + `CertificateCard` + `GateCard` + tests.

## Fuera de alcance (YAGNI / fases posteriores)

- **F5b-2:** bandeja global de acciones (todas las pendientes) + el **foso** (métricas de calibración `GET /v2/calibration/metrics` + etiquetar familias `PATCH /v2/defects/{id}/label`; requiere F5a/#22 en main).
- HTML imprimible del certificado (auth en iframe); lista/histórico de runs (sin endpoint); `POST /v2/certificates/verify` (auditor); **F6** (demo).
