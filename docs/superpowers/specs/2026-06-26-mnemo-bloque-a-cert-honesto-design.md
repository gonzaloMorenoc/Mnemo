# Mnemo — Bloque A: certificado honesto + self_eval + salvaguardas (diseño)

**Fecha:** 2026-06-26 · **Origen:** análisis de vendibilidad/IA `docs/auditoria/2026-06-26-sintesis-vendibilidad-ia.md` (§6, Bloque A) · **Rama:** `feat/mnemo-cert-honesto` (desde `main`)

## Objetivo

Cerrar la brecha de **credibilidad** que el análisis identificó como bloqueante para el concurso y para la venta: el certificado firma hoy un "dictamen de aptitud" que produce un if-ladder (pasivo legal), la pieza de IA estrella (`self_eval`) está vacía (`certificate.py:63` → `self_eval: None`), y la terminología ("defecto real novedoso" = fingerprint nunca visto) es deshonesta. Este bloque convierte el certificado en un **acta de evidencia reproducible con auto-evaluación firmada** que es honesta sobre su propia confianza — la base sobre la que descansan la demo y el pitch.

## Decisiones (confirmadas con el usuario)

- **Reencuadre:** el certificado pasa de "dictamen apto/no-apto" a **"acta de evidencia + evaluación del motor + sign-off"** con disclaimer. El campo `verdict` se mantiene (no romper consumidores) pero se recontextualiza como *evaluación del motor*, no garantía.
- **self_eval:** **métricas deterministas** del motor (precisión por tenant desde `triage_corrections`, composición del run, tamaño de muestra). Sin LLM-judge (eso es el Bloque B). 0€, auditable, firmado.
- **Confianza modula el veredicto:** `self_eval.confidence == "low"` (cold-start o precisión baja) → un `apto` baja a `apto-con-reservas`. **No** se atenúa el `no-apto` (no silenciar fallos reales).
- **Alcance:** las 5 piezas, en **2 PRs**. **Pieza 4 = 4b** (salvaguarda + advertencia, sin ingesta del diff; 4a diferido como follow-up). **Pieza 5b = archivar** el RAG legacy (reversible), no eliminar.
- `DATABASE_URL` (.env) = **producción** (tests de integración). main protegida (PR por fase). Determinista (sin LLM en el camino del certificado). TDD por subagentes. Commits con la línea `Claude-Session`.

> **Nota de integración:** el bloque sale de `main` (d82f54a), sin PR-A (#25) ni PR-B (#26). PR-2 toca `actions/service.py` y PR-B también (B2); si ambos se mergean, rebasar para resolver el solape en `actions/service.py`.

---

## PR-1 — El certificado honesto (`src/certify/`, `src/api_v2.py` gate)

Cohesivo: todo gira en torno a `certify/` y la política de veredicto compartida cert↔gate.

### Pieza 1 — `self_eval` determinista, firmado

`build_certificate` (`src/certify/certificate.py`) sigue siendo **puro**: recibe el `self_eval` ya computado (el servicio inyecta los datos, como ya hace con `created_at`). El `CertificateService` (`src/certify/service.py`) computa el bloque a partir de:
- **`engine_calibration`** ← `AssuranceRepository.get_calibration_metrics(user_id, org_id)` (ya existe): `tenant_accuracy` (= su `accuracy`), `n_corrections` (= su `total`), `por_categoria_humana` (= su `por_categoria`).
- **`run_composition`** ← contar sobre los verdicts del run: `total`, `llm_assisted` (verdicts con `llm_assisted=True`), `deterministic` (resto). Transparencia de cuánto dependió del LLM.
- **`confidence`** ← derivado por umbrales (constantes en `certificate.py`): `low` si `n_corrections < 30` **o** `tenant_accuracy < 0.60`; `high` si `n_corrections >= 100` **y** `tenant_accuracy >= 0.80`; `medium` en otro caso.

Estructura del bloque (reemplaza `self_eval: None`):
```json
"self_eval": {
  "method": "deterministic_v1",
  "engine_calibration": {"tenant_accuracy": 0.93, "n_corrections": 412, "por_categoria_humana": {"real": 120, …}},
  "run_composition": {"total": 20, "deterministic": 18, "llm_assisted": 2},
  "confidence": "high",
  "evaluated_at": "<created_at inyectado>"
}
```
Se firma automáticamente (entra en `canonical_json`). `build_certificate` gana un parámetro `self_eval: Dict` (en vez del literal `None`).

### Pieza 2 — reencuadre a "acta de evidencia"

En `build_certificate`: `schema: "mnemo.cert.v2"`; añadir `attestation_type: "evidence_and_assessment"` y `disclaimer` (constante, texto exacto):
> *"Este certificado es un acta de evidencia reproducible: registra los fallos observados, la evaluación del motor de triaje (determinista, auditable) y las aprobaciones humanas. La 'evaluación' es una señal asistida, no una garantía de ausencia de defectos ni una certificación de aptitud legal."*

`render_html` (`src/certify/render.py`): título y un bloque de disclaimer visible; presentar `verdict` como "Evaluación del motor" (no "Veredicto: APTO"). Mantener `verdict` como clave del JSON (consumidores/tests).

### Pieza 3 — la confianza modula el veredicto + terminología honesta

- **Modulación:** `compute_verdict` (`certificate.py`) gana un parámetro `confidence: str = "high"`. Tras calcular el veredicto base, si `confidence == "low"` y el resultado sería `apto`, devuelve `apto-con-reservas`. `no-apto` y `apto-con-reservas` no cambian. **Cert y gate comparten esta función** (es la única fuente de la política §7.1): `build_certificate` pasa su `confidence`; el `GateService`/endpoint (`api_v2.py`) también computa el `confidence` (vía `get_calibration_metrics`) y lo pasa, para que cert y gate no diverjan.
- **Terminología:** en `render_html` (y en cualquier etiqueta de cara al usuario), mapear `rule_applied == "R5_real_novel"` → **"real (sin precedente en el histórico)"**. El JSON `evidence` mantiene `rule_applied` literal (auditable); solo cambia la **presentación**. (No se toca `engine.py`: la regla interna es la misma.)

---

## PR-2 — Salvaguardas + higiene (`src/actions/`, `src/llm/`, repo)

### Pieza 4 (4b) — self-heal anti-enmascaramiento

Riesgo: un bug real puede cambiar el DOM → clasificarse "mantenimiento" → el self-heal reescribe el locator y **oculta la regresión**. Sin ingerir el diff del commit (4a, diferido), la mitigación factible:
- **Advertencia explícita** en el cuerpo del PR de self-heal (`_self_heal_body` en `src/actions/service.py`): una nota visible *"⚠️ Verificar: si este cambio de UI proviene de un cambio en el código de producción, curar el locator podría enmascarar una regresión real. Confirmar que es un cambio de UI legítimo antes de aprobar."*
- **Marca en la evidencia:** el `evidence` del certificado / la acción señala los heals de mantenimiento como `masking_risk: true` para que el revisor humano lo vea.
- Confirmar que R3 (maintenance) ya exige `not assertion_failure` (fix de F2) — si una aserción real co-ocurre, no se clasifica mantenimiento. (Verificación, no cambio.)

> 4a (follow-up, fuera de este bloque): ingerir los archivos cambiados del commit (reporter o GitHub compare API) → señal `commit_touched_prod` → R3 cede si el commit tocó código de producción de la ruta bajo prueba.

### Pieza 5 — higiene

- **5a — modelo LLM por defecto:** en `src/llm/factory.py`, sustituir el alias obsoleto `claude-3-5-haiku-latest` por `claude-haiku-4-5-20251001` (vigente) en `_DEFAULT_MODELS` para Anthropic. Ollama local sigue siendo el default on-premise; esto solo afecta cuando `ALLOW_EXTERNAL_LLM` está activo. Cambio de config + test.
- **5b — archivar el RAG legacy:** mover los artefactos del producto anterior ("SmartErrorDebugger" / RAG) a un directorio `legacy/` para que el repo cuente **un** producto. Candidatos: `api.py` (monta `BugAnalyzer`/`qa_chain`), `docs/DEMO.md`, `scripts/seed_demo.py`, y los módulos RAG que solo ellos usan. **Alcance conservador:** mover **solo** lo que el Autopilot (`src/api_v2.py`, `src/triage/`, `src/actions/`, `src/certify/`, `src/defects/`) no importe; verificar con un grep de imports antes de mover. Si un módulo es compartido, no se mueve. Añadir `legacy/README.md` explicando que es el producto anterior, conservado por historia.

---

## Testing (TDD)

- **PR-1:** `build_certificate` produce `self_eval` con los tres niveles de `confidence` (high/medium/low) según umbrales; `compute_verdict(..., confidence="low")` baja `apto`→`apto-con-reservas` y deja `no-apto`/`apto-con-reservas` intactos; el certificado firmado **incluye** `self_eval` y la firma verifica sobre el cert con el bloque; `render_html` muestra el disclaimer y la etiqueta "real (sin precedente…)"; el `CertificateService` integra `get_calibration_metrics` (integración con BD: un tenant con correcciones → `engine_calibration` poblado; un tenant nuevo → `confidence: low`). Gate alineado: `GateService` pasa el `confidence` (cert↔gate no divergen).
- **PR-2:** el `_self_heal_body` de un heal de mantenimiento incluye la advertencia; el `evidence`/acción marca `masking_risk`; `factory.py` devuelve el modelo vigente; archivar el legacy **no rompe** la suite (`python3 -m pytest -m "not integration"` verde) ni los imports del Autopilot.

## Fuera de alcance (Bloques B/C/D)

- LLM-judge/RAGAS y las apuestas generativas (causa-raíz multimodal, NL sobre Defect DNA, reparación LLM+AST) — **Bloque B**.
- Demo e2e de 3 actos, ROI en pantalla, PDF del certificado, aislamiento en vivo — **Bloque C**.
- Narrativa/categoría + las 3 métricas del pitch — **Bloque D**.
- 4a (señal `commit_touched_prod` desde el diff) — follow-up.
