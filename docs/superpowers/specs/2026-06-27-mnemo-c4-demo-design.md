# Mnemo — Bloque C · C4: guion + self-heal en vivo + aislamiento A/B (diseño)

**Fecha:** 2026-06-27 · **Parte de:** Bloque C (demo del concurso), sub-PR 4 de 4 (ÚLTIMO) · **Base:** `main` 58086f0 · **Backend:** Python · **Frontend:** Next.js/TS.

## Contexto

C1 sembró la demo (Org A "Demo MTP" + Org B "Cliente Beta", 3 escenarios pre-procesados, `fresh_push.json` reservado). C2 dio el run view (briefing+ROI). C3 el PDF. C4 cierra el Bloque C: el **guion de la demo**, el **self-heal en vivo** (Acto 1→3 completo) y el **aislamiento A/B visible en la UI**.

Hallazgos del recon:
- `fresh_push.json` = `checkout-suite/test_perfil`, `status fail`, `NoSuchElementError "locator not found: #guardar"`, DOM con `<button id="guardar-cambios">`. Sin green baseline → R6 ambiguous (gate rojo). **Con** un baseline verde previo (donde existía `#guardar`) → `locator_error + has_green_baseline + dom_changed` → **R3 maintenance** → self-heal propone `#guardar`→`#guardar-cambios`.
- La UI toma **siempre la primera org** (`orgsQuery.data?.[0]?.id`) — no hay selector de organización. Páginas afectadas: `autopilot`, `assurance`, `defects`, `calibration`.
- Aislamiento ya probado a nivel RLS (`test_rls_behavioral.py`).

## Objetivo

Que la demo se ejecute de principio a fin con un **clímax real** (self-heal de mantenimiento en vivo) y muestre el **aislamiento multi-cliente en pantalla** (cambiar de Org A a Org B), con un **guion + runbook** para no improvisar.

## Decisiones (confirmadas)

- **Self-heal en vivo:** sembrar un **green baseline** de `checkout-suite/test_perfil` para que el push en vivo de `fresh_push.json` caiga en R3 maintenance.
- **Aislamiento A/B:** **añadir un selector de organización a la UI** (switcher en el topbar) — cambiar A↔B en pantalla muestra que cada cliente solo ve lo suyo.
- **Guion 3 actos + runbook** en `docs/demo/`.

## Componentes

### 1. Green baseline (backend/datos) — `src/demo/seed.py` + `scripts/demo_fixtures/`
Nuevo fixture `perfil_green.json`: `checkout-suite/test_perfil`, `status pass`, `commit_sha` previo (p.ej. `demo-perfil-baseline`), DOM con el locator **bueno** (`<form id="perfil"><button id="guardar">Guardar</button></form>`). `seed_demo` lo ingesta en Org A **antes** de reservar `fresh_push` (así existe la baseline verde). `fresh_push.json` se mantiene reservado (no ingerido): el push en vivo lo ingesta y, gracias al baseline, da R3 maintenance. Verificación: ejecutar `classify_error` + `triage_run` sobre `fresh_push` con el baseline sembrado → categoría `maintenance` (R3), como se validó en C1.

### 2. Selector de organización (frontend)
- **`OrgProvider`** (`frontend/src/components/providers/org-provider.tsx`): context que carga `getOrganizations`, mantiene `activeOrgId` (default = primera org), lo persiste en `localStorage`, y expone `useActiveOrg() -> { orgs, activeOrgId, setActiveOrgId }`. Montado dentro del árbol autenticado (junto a `auth-provider`).
- **`OrgSwitcher`** (`frontend/src/components/layout/org-switcher.tsx`): un dropdown (shadcn) en el `Topbar` con las orgs; al elegir una, `setActiveOrgId`. Si solo hay una org, se muestra el nombre sin dropdown.
- **Migración:** `autopilot/page.tsx`, `assurance/page.tsx`, `defects/page.tsx`, `calibration/page.tsx` dejan de usar `orgsQuery.data?.[0]?.id` y usan `useActiveOrg().activeOrgId`. (Quitan su `orgsQuery` propio si el provider lo cubre.)

### 3. Guion + runbook (docs) — `docs/demo/`
- **`docs/demo/guion.md`**: los 3 actos con qué se teclea / qué se ve / qué se dice:
  - **Acto 1 — el problema:** push en vivo (`fresh_push.json` vía el webhook) → triaje automático lo marca **maintenance** → el gate del release queda **rojo** (certificado no-apto). "Un cambio de DOM rompió el test; el sistema lo detecta solo."
  - **Acto 2 — la acción:** el self-heal propone el parche del locator (`#guardar`→`#guardar-cambios`); el humano aprueba (Nivel 2). Se enseña el certificado y su **PDF** (C3) + el **briefing** ejecutivo (C2).
  - **Acto 3 — el aprendizaje y el aislamiento:** re-run → gate **apto**; el panel de calibración (el "foso") muestra la precisión por cliente; se cambia a **Org B** con el selector → solo ve lo suyo (aislamiento multi-cliente). Cierre con el **ROI** (C2).
- **`docs/demo/runbook.md`**: cómo levantar todo para el ensayo (variables de entorno, `docker-compose` / arranque, correr el seed, abrir el frontend, el comando del push en vivo), una checklist pre-demo, y el plan B si algo falla (datos pre-sembrados de Org A respaldan cada acto).

## Garantías

- **Honestidad:** el self-heal en vivo usa el pipeline real (webhook→triaje→cert→gate de H2); nada está trucado. El baseline verde es un run legítimo.
- **Aislamiento real:** el selector cambia la org de las consultas; el backend (RLS + membership) garantiza que Org B no ve Org A.
- **Plan B:** si el push en vivo falla, los datos pre-sembrados de Org A (C1) cubren cada acto.
- **Sin romper lo existente:** la migración al `OrgProvider` mantiene el comportamiento por defecto (primera org) cuando no se cambia de selección.

## Testing

- **Backend:** el seed siembra el green baseline (un run verde de `checkout-suite/test_perfil` en Org A); con él, `fresh_push` clasifica `maintenance` (R3) — test que ejecuta classify+triage sobre el payload real (patrón de C1). `python3 -m pytest -m "not integration"`.
- **Frontend (vitest):** `OrgProvider`/`useActiveOrg` (default primera org; `setActiveOrgId` persiste); `OrgSwitcher` (lista orgs, cambia la activa); una página migrada usa la org activa (no `data[0]`). `npm test` + `tsc`.
- **Guion/runbook:** revisión humana (no testeable); el ensayo valida el flujo e2e.

## Fuera de alcance

- Bloque D (pitch/categoría/monetización; bloqueado por la base 11).
- Grabar el vídeo de la demo; rediseño de la UI más allá del switcher.
