# Mnemo — Bloque C · C1: seed de demo (diseño)

**Fecha:** 2026-06-27 · **Parte de:** Bloque C (demo del concurso), sub-PR 1 de 4 · **Base:** `main` 94d7f95 (motor arranca e2e tras H2) · **Backend:** Python.

## Contexto y descomposición del Bloque C

El Bloque C (la demo del concurso, deadline 30-oct-2026) se descompone en 4 sub-PRs, cada uno con su spec→plan→PR:
- **C1 (este) — seed de demo:** dejar el sistema en un estado demostrable (3 escenarios + 2ª org).
- **C2 — UI de la demo:** briefing de B5 + panel de ROI en el run view (frontend).
- **C3 — PDF del certificado** descargable.
- **C4 — guion 3 actos + aislamiento A/B + ensayo.**

Guion objetivo (lo sirve todo el bloque): Acto 1 push→gate ROJO automático · Acto 2 triaje+acción (humano aprueba) · Acto 3 re-run→certificado APTO + el foso.

## Objetivo de C1

Que `docker compose up` deje el sistema **demostrable al abrir la UI**: la org de demo con los 3 escenarios ya triados/certificados, una 2ª org para el aislamiento, y un artefacto "fresco" reservado para el push en vivo del Acto 1.

## Decisiones (confirmadas)

- **Estado tras el seed:** los 3 escenarios quedan **pre-procesados** (triaje + certificado) → la UI muestra todo al abrir, sin depender de la red en vivo. Además se **reserva un artefacto fresco sin procesar** para el push del Acto 1 en directo (mantiene el "momento mágico" sin fragilidad).
- **Fixtures** de demo en archivos JSON versionados (`scripts/demo_fixtures/`).
- **Módulo** `src/demo/seed.py` reutilizable y testeable (extraído del `_seed` inline de `docker_init`).
- **Determinismo del seed:** los 3 escenarios se diseñan para clasificarse por las reglas DETERMINISTAS del triaje (R0–R6), sin depender del LLM → el seed no requiere Ollama en el arranque.
- Idempotente; `DATABASE_URL`=prod (el seed corre en el init dockerizado / contra prod con cuidado); commits con `Claude-Session`.

## Componentes

### 1. `scripts/demo_fixtures/` (artefactos JSON)
Los datos de los 3 escenarios como `CiRunArtifact` (el formato real del CI, con `dom` donde aplica):
- **Flaky** (`flaky.json`): `test_checkout` con timeouts intermitentes — varios resultados/runs que generan el patrón flaky (recurrencia que el triaje marca flaky por regla).
- **Mantenimiento** (`maintenance_green.json` + `maintenance_red.json`): `test_login` — un run verde con el DOM que contiene el locator bueno (`#submit`) y un run rojo con el DOM cambiado (`#send`), de modo que el self-heal infiera el cambio de locator.
- **Defecto real** (`real.json`): `test_export` con un fallo novel (p.ej. `NullPointerException`/500) cuyo fingerprint no se ha visto → real novel (gate rojo).
- **Fresco** (`fresh_push.json`): un artefacto reservado, NO procesado por el seed, para el push en vivo del Acto 1.

### 2. `src/demo/seed.py`
Funciones puras/orquestadoras (sin los `os.environ` de arranque, para ser testeable):
- `seed_demo(*, conn_or_url, demo_user_id) -> dict`: crea **Org A "Demo MTP"** (idempotente) e ingiere los artefactos flaky/maintenance/real (vía `IngestionService`/`ingest_artifact`); luego **pre-procesa** cada run: `TriageService.triage_run` + `CertificateService.generate` (firma local). El gate (publicación del check run en GitHub) se OMITE en el seed (la demo local no tiene GitHub App; la UI muestra el veredicto del certificado, que es determinista). Crea **Org B "Cliente Beta"** con datos propios distintos (1-2 fallos) para el aislamiento. NO procesa `fresh_push.json` (queda para el Acto 1).
- Devuelve un resumen (`{org_a, org_b, runs, fresh_artifact_path}`) para logging/verificación.

### 3. `scripts/docker_init.py`
`_seed` pasa a llamar `src.demo.seed.seed_demo(...)` (en vez del seed inline actual), manteniendo `main()` (`_wait_db` → `_apply_migrations` → `_ensure_demo_user` → seed). El init dockerizado queda con el sistema demostrable.

## Garantías

- **Idempotencia:** si Org A ya existe, el seed no duplica (como hoy).
- **Sin dependencia del LLM:** los escenarios se clasifican por reglas deterministas; el seed no necesita Ollama (robusto en el arranque).
- **Aislamiento real:** Org A y Org B son orgs separadas con membership distinta → C4 demostrará que no se ven entre sí (apoyado por el RLS conductual de BH3).
- **Determinismo del cert:** el pre-procesado usa el certificado firmado (determinista); no se inventan datos.

## Testing

- **Unit de las fixtures:** cada JSON valida contra `CiRunArtifact` (Pydantic) — los 3 escenarios + el fresco son artefactos válidos; el de mantenimiento tiene `dom` en verde y rojo.
- **Integración de `seed_demo`** (contra la BD, con cleanup): tras sembrar, Org A tiene los 3 runs con veredictos esperados (flaky/maintenance/real) y certificados emitidos; Org B existe con sus datos; `fresh_push.json` NO está ingerido; re-ejecutar es idempotente (no duplica).
- Tests con cleanup en fixtures. `python3 -m pytest`.

## Fuera de alcance (otros sub-PRs)

- **C2:** la UI (briefing de B5 + ROI en el run view).
- **C3:** el PDF del certificado.
- **C4:** el guion de 3 actos, el push en vivo del Acto 1 (usa `fresh_push.json`), la demostración del aislamiento A/B, el ensayo.
- Bloque D (pitch).
