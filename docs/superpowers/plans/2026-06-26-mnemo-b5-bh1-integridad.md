# Bloque B.5 · BH1 — Integridad del veredicto — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el LLM-judge deje de modular el veredicto FIRMADO — `ai_eval` pasa a ser dato informativo firmado, el veredicto vuelve a ser determinista y reproducible.

**Architecture:** Eliminar el único puente `ai_eval → confidence` en `compute_self_eval` (`src/certify/certificate.py`). `compute_confidence`/`compute_verdict` ya son deterministas y no se tocan. `ai_eval` sigue dentro del `self_eval` firmado.

**Tech Stack:** Python, pytest.

## Global Constraints

- **Determinismo donde firmo:** tras este PR, el veredicto es función pura de (cold-start `n<30`, `accuracy<0.60`, veredictos de triaje). `ai_eval` NO lo modula.
- `ai_eval` sigue presente en el `self_eval` (firmado, informativo, evaluable por el judge) — su firma debe seguir cubriéndolo.
- El judge (`src/ai/judge.py`) y `service.py` (cálculo/inyección de `ai_eval`) NO cambian funcionalmente.
- `python3 -m pytest`. Commit `fix:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: Desacoplar `ai_eval` del veredicto firmado

**Files:**
- Modify: `src/certify/certificate.py` (`compute_self_eval`, docstring, constante `_LOW_FAITHFULNESS`)
- Test: `tests/test_certificate.py` (invertir un test + añadir el de determinismo)

**Interfaces:**
- `compute_self_eval(*, calibration, verdicts, created_at, ai_eval=None) -> Dict` — la firma NO cambia; cambia el comportamiento (`ai_eval` deja de afectar `confidence`).
- `compute_confidence`, `compute_verdict` — sin cambios.

- [ ] **Step 1: Invertir el test que asume la degradación + añadir el de determinismo** en `tests/test_certificate.py`.

Reemplazar el test actual (líneas ~66-72, `test_self_eval_includes_ai_eval_and_low_faithfulness_forces_low_confidence`):

```python
def test_self_eval_includes_ai_eval_but_does_not_modulate_confidence():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}   # determinista: "high"
    ai = {"method": "llm_judge", "faithfulness": 0.3, "groundedness": 0.4, "n": 2, "evaluated_at": "t"}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": True}], created_at="t", ai_eval=ai)
    assert se["ai_eval"] == ai                 # ai_eval sigue presente (informativo, firmado)
    assert se["confidence"] == "high"          # NO lo degrada: el confidence es el determinista
```

Y añadir, a continuación, el test de determinismo:

```python
def test_verdict_identical_with_and_without_ai_eval():
    from src.certify.certificate import compute_self_eval, compute_verdict
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}        # "high"
    verdicts = [{"category": "flaky", "llm_assisted": True}]    # sin real/maintenance/approval → apto si confidence high
    se_none = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="t", ai_eval=None)
    ai_bad = {"faithfulness": 0.1, "groundedness": 0.1, "n": 1}
    se_ai = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="t", ai_eval=ai_bad)
    assert se_none["confidence"] == se_ai["confidence"] == "high"        # ai_eval no modula
    v_none = compute_verdict(verdicts, confidence=se_none["confidence"])
    v_ai = compute_verdict(verdicts, confidence=se_ai["confidence"])
    assert v_none == v_ai == "apto"                                       # veredicto reproducible
```

(Los tests `test_self_eval_ai_eval_none_keeps_deterministic_confidence` (~74) y `test_high_faithfulness_does_not_inflate` (~80) SIGUEN VÁLIDOS sin cambios — el primero ya prueba el caso None; el segundo prueba cold-start→low, que ahora viene solo del determinista. NO los toques. El de firma `test_signature_covers_ai_eval` (~103) también sigue válido — confirma que `ai_eval` sigue firmado.)

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_certificate.py -q`. Esperado: el nuevo `test_self_eval_includes_ai_eval_but_does_not_modulate_confidence` falla (el código actual da `"low"`) y `test_verdict_identical_with_and_without_ai_eval` falla (el código actual da `apto-con-reservas` para `se_ai`).

- [ ] **Step 3: Quitar el puente `ai_eval → confidence`** en `src/certify/certificate.py`.

En `compute_self_eval`, eliminar estas dos líneas (~38-39):

```python
    if ai_eval is not None and ai_eval.get("faithfulness", 1.0) < _LOW_FAITHFULNESS:
        confidence = "low"
```

de modo que quede:

```python
def compute_self_eval(*, calibration: Dict[str, Any], verdicts: List[Dict[str, Any]],
                      created_at: str, ai_eval: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Auto-evaluación del motor (deterministic_v1) + ai_eval opcional del LLM-judge. Pura.
    ai_eval es INFORMATIVO: se firma dentro del self_eval pero NO modula el veredicto
    (el confidence depende solo de la calibración determinista — "determinismo donde firmo")."""
    total = len(verdicts)
    llm_assisted = sum(1 for v in verdicts if v.get("llm_assisted"))
    confidence = compute_confidence(calibration)
    return {
        "method": "deterministic_v1",
        ...
```

(El resto del dict devuelto, incluido `"ai_eval": ai_eval`, NO cambia.)

Luego elimina la constante `_LOW_FAITHFULNESS = 0.5` (línea ~13) — queda sin uso. Verifica con `grep -rn "_LOW_FAITHFULNESS" src/` que no la usa nadie más antes de borrarla; si algún otro módulo la importa, déjala y solo quita su uso aquí.

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_certificate.py -q` → PASS. Luego la suite: `python3 -m pytest -m "not integration" -q` → green. Si algún otro test (p.ej. en `tests/test_certify_service_aieval.py` o `tests/test_evaluation.py`) asumía la degradación por `ai_eval`, ajústalo al nuevo contrato (ai_eval informativo, no modulador) — pero NO debilites las aserciones de que `ai_eval` está presente/firmado ni las de degradación por calibración determinista.

- [ ] **Step 5: Commit**

```bash
git add src/certify/certificate.py tests/test_certificate.py
git commit -m "fix(certify): ai_eval del LLM-judge es informativo, no modula el veredicto firmado

Restaura 'determinismo donde firmo': el veredicto vuelve a depender solo de
señales deterministas (cold-start, accuracy del tenant) y es reproducible.
ai_eval sigue firmado dentro del self_eval como dato evaluable por el judge.

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **Por qué importa:** un certificado vendido como "acta de evidencia **reproducible**" no podía serlo si un LLM no-determinista movía su veredicto entre reruns. Este PR cierra esa contradicción (hallazgo H1 de la auditoría, marcado por dos lentes).
- **Lo que NO cambia:** el judge sigue corriendo; `ai_eval` sigue en el `self_eval` firmado (visible y auditable); la degradación por baja calibración del motor (cold-start / accuracy) se mantiene — esa SÍ es determinista.
- **Fuera de alcance:** BH2 (seguridad), BH3 (tests), y los demás bloques.
