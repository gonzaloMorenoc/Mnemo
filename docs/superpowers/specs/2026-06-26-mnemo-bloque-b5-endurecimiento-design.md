# Mnemo — Bloque B.5: endurecimiento (diseño maestro)

**Fecha:** 2026-06-26 · **Origen:** auditoría de estado `docs/auditoria/2026-06-26-estado-post-bloque-b/` · **Base:** `main` 6929d77 (Tanda 1 + Bloque A + Bloque B completos) · **Backend:** Python/FastAPI.

## Objetivo

Cerrar los hallazgos de la auditoría que bloquean "credibilidad + seguridad + demostrar lo que vendemos", en **3 PRs independientes** desde `main`. No toca el motor: **restaura integridad, cierra seguridad, prueba el aislamiento**.

## Decisiones (confirmadas)

- **Agrupación: 3 PRs** — BH1 (integridad) · BH2 (seguridad) · BH3 (tests). Independientes; orden sugerido BH1→BH2→BH3, mergeables en cualquier orden.
- **Rol Nivel 2:** `owner` + `admin` (patrón de la migración 001).
- **Truncado AIRepair:** 8000 chars. **E-1:** `LANGCHAIN_TRACING_V2=false` por defecto. **Cobertura:** medir la actual y fijar `--cov-fail-under` justo por debajo.
- Determinismo del veredicto restaurado; on-premise/híbrido; `DATABASE_URL`=prod; main protegida; TDD por subagentes; commits con `Claude-Session`.

---

## PR BH1 — Integridad del veredicto (🔴 H1)

**Problema:** el LLM-judge contamina el veredicto FIRMADO. `compute_self_eval` (`src/certify/certificate.py:38-39`) hace `if ai_eval.faithfulness < 0.5: confidence = "low"`, y `compute_verdict` degrada `apto→apto-con-reservas` con `confidence=="low"`. Un LLM no-determinista mueve el veredicto en reruns → un certificado vendido como "acta de evidencia **reproducible**" no es reproducible. Rompe "determinismo donde firmo".

**Fix:**
- En `compute_self_eval`, **eliminar las líneas 38-39** (el puente `ai_eval → confidence`). `confidence = compute_confidence(calibration)` (puro, determinista). `ai_eval` se mantiene en el dict devuelto (línea 50) — sigue **firmado como dato informativo**, evaluable por el judge.
- `compute_confidence` y `compute_verdict` NO cambian (ya son deterministas; `compute_verdict` usa el confidence determinista).
- Actualizar el docstring (líneas 33-34) para reflejar que `ai_eval` es informativo, no modulador.
- `src/certify/service.py`: sigue calculando e inyectando `ai_eval` (informativo); sin cambio funcional salvo que ya no afecta el veredicto.

**Tests:**
- `compute_self_eval` con y sin `ai_eval` (incl. `faithfulness=0.1`) → el `confidence` y el `verdict` resultante son **idénticos** (prueba de determinismo); `ai_eval` sigue presente en el `self_eval`.
- Actualizar los tests de B1 que asumían la degradación por `ai_eval` (ahora `ai_eval` no cambia el veredicto).
- El veredicto firmado es función pura de (cold-start, accuracy, veredictos de triaje) — añadir/ajustar un test que lo fije.

---

## PR BH2 — Seguridad (🟠 A-1, E-1, E-2, I-1, S-3)

### A-1 — authz de Nivel 2
`approve_action` / `mark_materializing` / `reject_action` (`src/actions/repository.py:113/145/178`) solo exigen membership. Estas operaciones aprueban PRs que escriben código IA en el repo del cliente → deben exigir **`role in ('owner','admin')`**.
- Añadir el filtro de rol al chequeo de membership de esos tres métodos (`... and m.role in ('owner','admin')`), o un helper `_is_org_admin(conn, user_id, org_id)`.
- **Tests:** un `member`/`viewer` no puede aprobar/materializar/rechazar (devuelve `False`/no actúa); un `admin`/`owner` sí.

### E-1 — exfiltración por tracing
`.env.example:2` tiene `LANGCHAIN_TRACING_V2=true`, que envía todos los prompts a LangSmith saltándose `ALLOW_EXTERNAL_LLM`.
- Cambiar a `LANGCHAIN_TRACING_V2=false` (mantener el aviso de la línea 35).

### E-2 — código del cliente sin truncar
`src/actions/ai_repair.py:37` manda `test_source` entero al LLM.
- Truncar `test_source` a **8000 chars** antes de construir el `context` del prompt (constante `_MAX_SOURCE = 8000`).
- **Test:** un `test_source` > 8000 se trunca antes de llamar al provider.

### I-1 — inyección en el body del PR/Issue
La salida del LLM (`reasoning`/`explanation`) llega al **markdown** del body del PR/Issue (`_self_heal_body`, tickets de B2). El `new_block` es el parche (va al código, intencional); lo que se neutraliza es la inyección en el markdown.
- Sanear el texto del LLM que entra al body: neutralizar fences/markers de cierre (p.ej. limitar longitud + escapar ``` ``` ``` y `<!-- -->`). Aplica a `_self_heal_body` (`reasoning`) y al body del ticket si usa texto del LLM.
- **Test:** un `reasoning` con un fence/marker malicioso no rompe ni inyecta en el body resultante.

### S-3 — cota de input
`AskRequest.question` (y los demás `*Request` nuevos del Bloque B en `src/multitenant_models.py`) sin `max_length`.
- Añadir `Field(max_length=2000)` a `AskRequest.question` y revisar los otros Request del Bloque B.
- **Test:** una `question` > el límite es rechazada (422).

---

## PR BH3 — Tests/verificación (🟠 RLS conductual + cobertura)

### RLS conductual (P0)
Hoy `test_migration_016_rls.py` solo lee flags de `pg_class`; ningún test demuestra el aislamiento a nivel de policy. **Es la garantía que vende el producto.**
- Test de integración: crear org-A + org-B + un usuario miembro de B; abrir una conexión que **respete RLS** (rol `authenticated` + `request.jwt.claims` del usuario B, NO el bypass del pooler/service-role); intentar `select` sobre filas de org-A (p.ej. `defect_families`, `certificates`) → **0 filas**. Repetir para 2-3 tablas tenant clave. Demostrar que un miembro de B SÍ ve las suyas (control positivo).
- Cleanup en el fixture (orgs/usuarios efímeros, CASCADE).

### Cobertura en CI
`backend-ci.yml:39` corre `pytest -m "not integration"` sin medir cobertura.
- Añadir `pytest-cov`: `pytest -m "not integration" --cov=src --cov-report=term-missing --cov-fail-under=N`.
- **Medir la cobertura actual primero** y fijar `N` justo por debajo (p.ej. real 78 → `N=75`), para que falle ante regresiones futuras sin romper el build de hoy. Documentar el número medido en el PR.

---

## Fuera de alcance (bloques siguientes)

- **H2** (arranque e2e: `asgi.py` + entrypoint legacy + migraciones docker + webhook→gate→cert).
- **God-objects** (`defects/repository.py`, `api_v2.py`) + `BaseRepository`.
- **El foso** que componga el triaje; verificación pública del certificado (Vía B).
- **Bloque C** (demo) y **D** (pitch).
