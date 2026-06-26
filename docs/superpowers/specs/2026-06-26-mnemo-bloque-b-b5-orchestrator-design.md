# Mnemo — B5: agente orquestador (Release Assurance Briefing) (diseño)

**Fecha:** 2026-06-26 · **Bloque:** B (la IA como protagonista), apuesta 5 — **la última** · **Spec maestro:** `docs/superpowers/specs/2026-06-26-mnemo-bloque-b-ia-design.md` · **Rama:** `feat/mnemo-orchestrator` (desde `main` 24da344, con B1+B2+B3+B4)

## Objetivo

Cerrar el Bloque B con un **agente orquestador** que lee el run completo y produce un **Release Assurance Briefing**: una narrativa ejecutiva con recomendación accionable, citada a la evidencia determinista. Un QA Director lo lee en 30s y entiende qué pasó, por qué y qué hacer — sin tocar lo que el sistema firma.

## Decisiones (confirmadas)

- **Rol: briefing ejecutivo razonado** (no decisor de acciones, no conversacional). El orquestador **explica y conecta** triaje + causa-raíz (B2) + acciones/parches (B4) + certificado/self_eval (B1); NO decide el veredicto.
- **Determinismo donde firmo:** el `verdict` del briefing es SIEMPRE el del certificado firmado (no lo recalcula el LLM). Si la narrativa contradijera el veredicto, manda el certificado.
- **Forma:** endpoint backend `GET /v2/runs/{run_id}/briefing` (la UI va en el Bloque C).
- On-premise/híbrido (B1, Ollama local por defecto); membership-gated; `DATABASE_URL`=prod; TDD por subagentes; commits con `Claude-Session`.

## Componentes

### 1. Lectura agregada del run (`src/api_v2.py` / un helper)
Reúne, todo membership-gated y reusando lo existente:
- `get_run_assurance_data(user_id, run_id)` → `{run, summary, families}` (triaje: conteos por categoría, defectos reales con título/ocurrencias).
- `get_certificate(user_id, run_id)` → el veredicto firmado + `self_eval` (confidence/ai_eval de B1). Puede ser `None` (run sin certificar todavía).
- `get_actions(user_id, org_id, run_id=...)` → las acciones propuestas del run (tickets de B2, parches `ai_repair` de B4). Si `get_actions` no filtra por `run_id`, se añade ese filtro o un método `list_actions_for_run` membership-gated.
Construye un `run_data` con **ids citables**: `run`, `cert`, `family:<id>`, `action:<id>`.

### 2. `src/ai/briefing.py`
`generate_briefing(*, run_data, provider=None) -> Dict` con `{summary, verdict_line, highlights, recommendation, citations}`:
- Construye el contexto (cada pieza como `{id, content}`, datos NO confiables) y llama `generate_structured` (B1, `on_failure="none"`) pidiendo que cite los ids usados.
- Normaliza tipos (`highlights`/`citations` listas; `summary`/`recommendation`/`verdict_line` strings).
- **Degradación:** `generate_structured` → `None` (sin LLM) → briefing determinista por plantilla con los datos del run (p.ej. "Run <id>: <n> fallos — <m> real, <k> mantenimiento; veredicto <cert>; confianza <conf>."), `citations` con los ids disponibles. Nunca lanza.

### 3. Endpoint `GET /v2/runs/{run_id}/briefing` (`src/api_v2.py`)
Membership-gated (patrón de los endpoints del run). Lee el run agregado, llama `generate_briefing`, y devuelve `BriefingResponse{verdict, summary, recommendation, highlights, citations}`:
- **`verdict`** = el del certificado determinista (`certificate.verdict`), o `"sin certificar"` si no hay certificado — NUNCA el que invente el LLM.
- 404 si el run no existe / no es miembro; el LLM caído degrada (no 500).

## Garantías

- **Determinismo intacto:** el briefing es informativo; el veredicto firmado y el gate no se tocan ni se recalculan. El `verdict` de la respuesta proviene del certificado.
- **Citas + judge:** `citations` (ids de evidencia) → evaluable por el judge de B1; coherente con B2/B3.
- **Aislamiento por tenant:** todas las lecturas son membership-gated (como B3).
- **Privacidad/híbrido:** `get_llm_provider()` (Ollama local por defecto); el run_data va al prompt → con local no sale de la infra (`ALLOW_EXTERNAL_LLM`).
- **Degradación e2e:** sin LLM → briefing determinista; sin run → 404; el LLM nunca produce un 500.

## Testing (TDD)

- **`generate_briefing`:** unit con provider mock — narrativa con citas cuando el LLM responde; degradación a plantilla determinista (con los conteos + veredicto) cuando no hay LLM; normalización de tipos.
- **Endpoint:** dependency-overrides (sin LLM/DB reales) — 200 con `{verdict, summary, recommendation, highlights, citations}`; el `verdict` es el del certificado (mockeado), no el del LLM; run inexistente → 404; LLM caído → 200 con briefing determinista.
- **Lectura agregada / `list_actions_for_run`** (si se añade): integración membership-gated (acciones del run; no-miembro → []).
- Provider + repos mockeados; integración con cleanup. `python3 -m pytest`.

## Fuera de alcance (otros bloques)

- **UI del briefing** (Bloque C / demo).
- Multi-turno / chat sobre el run (eso es B3).
- Que el orquestador **decida** acciones o el veredicto (rompería el invariante).
