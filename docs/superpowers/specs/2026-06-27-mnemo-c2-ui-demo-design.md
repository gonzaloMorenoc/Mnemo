# Mnemo — Bloque C · C2: UI de la demo (briefing + ROI) (diseño)

**Fecha:** 2026-06-27 · **Parte de:** Bloque C (demo del concurso), sub-PR 2 de 4 · **Base:** `main` 94d7f95 · **Frontend:** Next.js/TS + react-query + shadcn/ui.

## Contexto

El run view rico vive en `frontend/src/app/app/autopilot/page.tsx` y ya monta `CertificateCard`, `GateCard`, `ActionsPanel`, `TriageVerdictList`, `RunSelector`. Faltan dos piezas para la demo: el **briefing de B5** (no hay endpoint en el cliente) y el **ROI en pantalla** (no existe). C2 los añade. (C1 = seed; C3 = PDF; C4 = guion/A-B.)

## Objetivo

Que el run view abra con un **resumen ejecutivo (briefing)** arriba y muestre el **ROI honesto** — lo que un comprador (QA Director) ve primero en la demo.

## Decisiones (confirmadas)

- **Briefing:** una `BriefingCard` arriba del run view (resumen ejecutivo: qué pasó, gravedad, recomendación, citado), alimentada por `GET /v2/runs/{id}/briefing` (B5).
- **ROI:** calculado en el **frontend** con un **supuesto explícito y visible** (minutos/fallo manual) — sin backend nuevo. `coste API: 0€/release` como propiedad de diseño (Ollama local).
- **Ubicación:** ambos en `autopilot/page.tsx`, reusando los componentes/estilo shadcn existentes.
- Verdict del briefing = el del certificado (determinista, viene del endpoint); honestidad del ROI (el supuesto se ve en pantalla).

## Componentes

### 1. Cliente API (`frontend/src/lib/api/endpoints.ts` + `types.ts`)
Añadir `getBriefing(token, runId) -> BriefingResponse` → `GET /api/v2/runs/{runId}/briefing`. Tipo `BriefingResponse { verdict: string; summary: string; recommendation: string; highlights: string[]; citations: string[] }` (espejo del backend B5).

### 2. `BriefingCard` (`frontend/src/components/autopilot/BriefingCard.tsx`)
Recibe el `runId`, hace `useQuery(getBriefing)`, y renderiza: un badge con `verdict`, el `summary`, la `recommendation` destacada, y los `highlights` como lista. Estados de carga/error (degrada: si el briefing falla, la tarjeta muestra un fallback discreto, NO rompe la página). Estilo shadcn (`Card`/`Badge`), coherente con `CertificateCard`.

### 3. `RoiPanel` (`frontend/src/components/autopilot/RoiPanel.tsx`)
Recibe los veredictos de triaje del run (ya cargados por el run view) y calcula:
- **Fallos auto-triados** = veredictos clasificados sin intervención humana (`requires_approval === false` y `category !== "unknown"`).
- **Horas ahorradas** = `auto_triados × MIN_POR_FALLO / 60`, con `MIN_POR_FALLO = 15` (constante **mostrada en pantalla** como supuesto, p.ej. "asumiendo 15 min de triaje manual por fallo").
- **Coste API** = `0 € / release` (etiqueta fija, propiedad de diseño on-premise).
Renderiza un panel con esas 3 cifras + la nota del supuesto (honestidad).

### 4. Integración en `autopilot/page.tsx`
`BriefingCard` arriba (tras el `RunSelector`, antes de las tarjetas de detalle); `RoiPanel` en una posición visible (junto al certificado/gate). Sin tocar la lógica existente de los otros componentes.

## Garantías

- **Degradación:** si `getBriefing` falla (LLM caído), la `BriefingCard` muestra un fallback y el resto del run view sigue funcionando.
- **Honestidad del ROI:** el supuesto (min/fallo) es visible; el coste 0€ se presenta como propiedad de diseño, no como número medido de API.
- **Sin backend nuevo:** C2 es solo frontend (el endpoint del briefing ya existe en B5).
- **Determinismo visible:** el `verdict` del briefing proviene del certificado firmado.

## Testing (vitest, patrón de `components/autopilot/__tests__`)

- **`getBriefing`:** llama al endpoint correcto y parsea `BriefingResponse`.
- **`BriefingCard`:** renderiza summary/recommendation/highlights/verdict de un briefing mock; muestra el fallback en error (no rompe).
- **`RoiPanel`:** con N veredictos auto-triados, calcula las horas esperadas (N×15/60) y muestra el supuesto + "0 €"; con 0 auto-triados, 0 horas sin romper.
- Tests con react-query/fetch mockeados (sin backend real). `npm test` (vitest) en `frontend/`.

## Fuera de alcance (otros sub-PRs)

- **C3:** PDF del certificado.
- **C4:** guion 3 actos, push en vivo (`fresh_push.json`), aislamiento A/B en vivo, ensayo.
- Cambios de backend (el endpoint del briefing es de B5); Bloque D (pitch).
