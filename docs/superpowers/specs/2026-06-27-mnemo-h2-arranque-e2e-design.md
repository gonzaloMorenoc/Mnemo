# Mnemo — H2: arranque e2e (diseño)

**Fecha:** 2026-06-27 · **Origen:** auditoría de estado (`docs/auditoria/2026-06-26-estado-post-bloque-b/`, hallazgo H2) · **Base:** `main` f599a19 (Tanda 1 + Bloque A + B + B.5) · **Backend:** Python/FastAPI. **Es el PREREQUISITO de la demo (Bloque C).**

## Objetivo

Que un `push` arranque el motor Autopilot de **extremo a extremo** en un despliegue limpio: el servicio sirve solo el Autopilot (con auth), la BD dockerizada tiene el esquema completo, y el webhook de CI emite certificado + gate automáticamente. Plumbing, no features.

## Decisiones (confirmadas)

- **Entrypoint:** nuevo `asgi.py` que monta SOLO el `v2_router`; `Dockerfile` CMD → `uvicorn asgi:app`. `api.py` deja de ser el arranque (los endpoints legacy sin auth salen del servicio); se conserva en el repo como deprecated — borrar el RAG v1 es limpieza aparte.
- **Lazo:** el `ci_webhook` emite cert + gate automáticamente tras el triaje (degradan si fallan).
- **Migraciones:** `docker_init.py` aplica TODAS por glob ordenado (no lista hardcodeada).
- **Alcance:** H2 = plumbing; el seed de demo + UI/ROI/PDF van al Bloque C.
- Determinismo intacto (cert/gate deterministas; acciones Nivel 2 siguen con approve); `DATABASE_URL`=prod; main protegida; TDD por subagentes; commits con `Claude-Session`.

## Componentes

### 1. `asgi.py` (nuevo) + `Dockerfile`
`asgi.py`: un `FastAPI(title="Mnemo Autopilot")` con `include_router(v2_router)` y nada más (sin los endpoints legacy de `api.py`, sin el `startup_event` del RAG v1 — el v2 usa getters lazy, no necesita startup). `Dockerfile`: `CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "8080"]`. El healthcheck (`/v2/health`) no cambia. `api.py` se mantiene en el repo (deprecated, ya no referenciado por el arranque).

### 2. `scripts/docker_init.py`
Sustituir la constante `MIGRATIONS` (lista 001-006) por la lectura de `sorted(glob("db/migrations/*.sql"))`, de modo que `_apply_migrations` aplique todas las migraciones presentes (001-016 y futuras) en orden. Mantener la idempotencia/manejo de errores existente.

### 3. `ci_webhook` (`src/api_v2.py`) + `CiWebhookResponse`
Tras el bloque de triaje (solo si `not result.get("deduplicated")` y hubo triaje), añadir dos pasos degradables (mismo patrón try/except → log que el triaje):
- **Cert:** `created_at = datetime.now(timezone.utc).isoformat(); cert = get_certificate_service().generate(user_id=CI_SERVICE_USER_ID, run_id=result["run_id"], created_at=created_at)`.
- **Gate:** `gate = get_gate_service().publish(user_id=CI_SERVICE_USER_ID, run_id=result["run_id"])`.
Cada uno en su try/except (un fallo de uno no impide el otro ni rompe el webhook). `CiWebhookResponse` gana `verdict: Optional[str]` (de `cert["verdict"]`) y `gate: Optional[str]` (estado/conclusión del gate), ambos `None` si degradaron. El webhook sigue devolviendo 200.

## Garantías

- **Invariante:** cert y gate son deterministas → automatizarlos en el webhook es coherente; las acciones de Nivel 2 (PRs/tickets) siguen requiriendo approve humano (no se tocan).
- **Degradación e2e:** sin firma configurada → cert degrada; sin GitHub App → gate degrada; el webhook responde 200 con lo que se pudo (`verdict`/`gate` = None).
- **Seguridad:** `asgi.py` monta solo el v2 (autenticado) → los endpoints legacy sin auth (`/analyze`, `/sync`, `/history`, `/evaluate`) quedan fuera del servicio.
- **Sin regresión:** el v2_router y sus tests no cambian; el webhook añade pasos, no altera ingest/triaje.

## Testing (TDD)

- **`asgi.py`:** `TestClient(asgi.app)` responde `/v2/health` (200) y NO expone `/analyze` (404) — el legacy quedó fuera.
- **`docker_init`:** el glob recoge todas las migraciones de `db/migrations/` en orden (incluye 007-016), no solo 001-006.
- **`ci_webhook`:** con un artefacto válido (firma OK, no deduplicado), tras el triaje se invocan `generate` (cert) y `publish` (gate) y la respuesta trae `verdict`/`gate` (servicios mockeados); si el gate falla (sin GitHub App) → `gate=None`, `verdict` presente, 200; si el cert falla → `verdict=None`, 200.
- Tests con servicios mockeados (sin GitHub/firma reales). `python3 -m pytest`.

## Fuera de alcance (bloques siguientes)

- **Bloque C:** seed de demo (3 escenarios + 2ª org), UI, ROI en pantalla, PDF del certificado, aislamiento A/B en vivo.
- Borrar el RAG v1 legacy (`api.py` + retriever/vector_store/structured_analyzer) + partir los God-objects — limpieza posterior.
- **Bloque D:** pitch.
