# Bloque B · PR-B1 — Base de generación + LLM-judge en self_eval + medición — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear la capa de generación híbrida `src/ai/`, añadir un LLM-judge cuyo score entra firmado en el `self_eval` (degradando el veredicto si la IA no es fiel), y arrancar la medición (golden set + eval-en-CI).

**Architecture:** Un helper `generate_structured` sobre el provider híbrido (Ollama local / Claude opt-in) con degradación elegante; un `judge` que lo usa para puntuar faithfulness/groundedness; `compute_self_eval` gana un sub-bloque `ai_eval` opcional que el `CertificateService` computa e inyecta; un golden set + script de eval cableado al CI.

**Tech Stack:** Python, pytest. Provider LLM mockeado en tests (sin LLM real).

## Global Constraints

- **Determinismo intacto:** el `ai_eval` es OPCIONAL y solo puede **degradar** el veredicto (apto→apto-con-reservas), nunca inflarlo. Si no hay LLM (Ollama caído / sin `ALLOW_EXTERNAL_LLM`), `ai_eval=None` y el `self_eval` determinista de #27 se mantiene **idéntico**.
- **Híbrido:** la generación usa `get_llm_provider()` (`src/llm/factory.py`) — Ollama local por defecto, Claude opt-in. Nunca en el camino firmado sin humano (aquí solo evalúa/firma una nota, no decide el veredicto base).
- **Degradación elegante** en todo: cualquier fallo del LLM → fallback determinista / `None`.
- `python3 -m pytest`; tests con provider MOCK. Commits `feat:` terminando con `Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok`.

---

## Task 1: `src/ai/generate.py` — `generate_structured` (base híbrida)

**Files:** Create `src/ai/__init__.py`, `src/ai/generate.py`; Test `tests/test_ai_generate.py`.

**Interfaces:** Produces — `generate_structured(*, prompt: str, context: List[Dict], schema: Dict[str, Any], provider=None, on_failure: str = "fallback") -> Optional[Dict[str, Any]]`. `schema` mapea `clave→valor_por_defecto`. `on_failure="fallback"` devuelve el schema con defaults; `on_failure="none"` devuelve `None`. `provider` debe tener `.complete(prompt) -> str` (el `LLMProvider` de `src/llm/provider.py`).

- [ ] **Step 1: Write the failing tests** — `tests/test_ai_generate.py`:

```python
from src.ai.generate import generate_structured


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _Boom:
    def complete(self, prompt): raise RuntimeError("llm down")


def test_parses_valid_json_and_fills_defaults():
    prov = _Provider('prefacio {"root_cause": "x", "confidence": 0.9} epilogo')
    out = generate_structured(prompt="p", context=[{"id": "e1", "content": "c"}],
                              schema={"root_cause": "", "confidence": 0.0}, provider=prov)
    assert out["root_cause"] == "x" and out["confidence"] == 0.9


def test_degrades_to_fallback_on_provider_error():
    out = generate_structured(prompt="p", context=[], schema={"root_cause": "", "confidence": 0.0},
                              provider=_Boom())
    assert out == {"root_cause": "", "confidence": 0.0}


def test_degrades_to_none_when_requested():
    assert generate_structured(prompt="p", context=[], schema={"x": 0.0},
                               provider=_Boom(), on_failure="none") is None


def test_garbage_output_degrades():
    out = generate_structured(prompt="p", context=[], schema={"x": 1},
                              provider=_Provider("no json aquí"), on_failure="none")
    assert out is None
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m pytest tests/test_ai_generate.py -q`.

- [ ] **Step 3: Implement** `src/ai/__init__.py` (empty) and `src/ai/generate.py`:

```python
import json
from typing import Any, Dict, List, Optional


def _build_context_block(context: List[Dict[str, Any]]) -> str:
    lines = []
    for item in context:
        cid = item.get("id", "?")
        content = item.get("content", "")
        lines.append(f"[{cid}] {content}")
    return "\n\n".join(lines[:10])


def _parse_json(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        raw = raw.get("text", "") or raw.get("output_text", "")
    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def generate_structured(*, prompt: str, context: List[Dict[str, Any]], schema: Dict[str, Any],
                        provider=None, on_failure: str = "fallback") -> Optional[Dict[str, Any]]:
    """Genera JSON estructurado con el provider híbrido; degrada según on_failure
    ('fallback' → schema con defaults; 'none' → None) ante cualquier fallo del LLM."""
    def _fail():
        return None if on_failure == "none" else {k: v for k, v in schema.items()}

    if provider is None:
        try:
            from src.llm.factory import get_llm_provider
            provider = get_llm_provider()
        except Exception:  # noqa: BLE001 — sin provider → degrada
            return _fail()
    full = f"{prompt}\n\nContext snippets:\n{_build_context_block(context)}"
    try:
        raw = provider.complete(full)
    except Exception:  # noqa: BLE001 — LLM caído → degrada
        return _fail()
    parsed = _parse_json(raw)
    if parsed is None:
        return _fail()
    out = {k: v for k, v in schema.items()}
    for k in schema:
        if k in parsed:
            out[k] = parsed[k]
    return out
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_ai_generate.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/ai/__init__.py src/ai/generate.py tests/test_ai_generate.py
git commit -m "feat(ai): generate_structured — capa de generación híbrida con degradación elegante

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 2: `src/ai/judge.py` — LLM-judge (faithfulness/groundedness) + `compute_ai_eval`

**Files:** Create `src/ai/judge.py`; Test `tests/test_ai_judge.py`.

**Interfaces:** Consumes — `generate_structured` (Task 1). Produces — `judge_output(*, claim: str, evidence: List[Dict], provider=None) -> Optional[Dict[str, float]]` (`{"faithfulness", "groundedness"}` o `None` si no hay LLM); `compute_ai_eval(*, verdicts: List[Dict], created_at: str, provider=None, judge_model: str = "") -> Optional[Dict]` que juzga los veredictos `llm_assisted` del run y agrega.

- [ ] **Step 1: Write the failing tests** — `tests/test_ai_judge.py`:

```python
from src.ai.judge import judge_output, compute_ai_eval


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


def test_judge_returns_scores():
    prov = _Provider('{"faithfulness": 0.8, "groundedness": 0.7}')
    out = judge_output(claim="es flaky", evidence=[{"id": "e1", "content": "retry pasó"}], provider=prov)
    assert out == {"faithfulness": 0.8, "groundedness": 0.7}


def test_compute_ai_eval_none_when_no_llm_assisted():
    verdicts = [{"category": "flaky", "llm_assisted": False, "evidence_bundle": {}}]
    assert compute_ai_eval(verdicts=verdicts, created_at="t", provider=_Provider("{}")) is None


def test_compute_ai_eval_aggregates_llm_assisted():
    prov = _Provider('{"faithfulness": 0.6, "groundedness": 0.6}')
    verdicts = [{"category": "real", "llm_assisted": True, "evidence_bundle": {"x": 1}, "rule_applied": "R6_ambiguous"}]
    out = compute_ai_eval(verdicts=verdicts, created_at="t", provider=prov, judge_model="m")
    assert out["method"] == "llm_judge" and out["n"] == 1
    assert out["faithfulness"] == 0.6 and out["judge_model"] == "m" and out["evaluated_at"] == "t"


def test_compute_ai_eval_none_when_provider_missing():
    verdicts = [{"category": "real", "llm_assisted": True, "evidence_bundle": {}}]
    # provider que lanza → judge None para todos → ai_eval None
    class _Boom:
        def complete(self, p): raise RuntimeError("down")
    assert compute_ai_eval(verdicts=verdicts, created_at="t", provider=_Boom()) is None
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Implement** `src/ai/judge.py`:

```python
from typing import Any, Dict, List, Optional

from src.ai.generate import generate_structured

_JUDGE_PROMPT = (
    "Eres un evaluador de calidad de QA. Dada una AFIRMACIÓN producida por un asistente y la "
    "EVIDENCIA disponible, puntúa de 0.0 a 1.0:\n"
    "- faithfulness: ¿la afirmación se sostiene SOLO en la evidencia, sin inventar?\n"
    "- groundedness: ¿está fundamentada en hechos concretos de la evidencia?\n"
    'Devuelve SOLO JSON: {"faithfulness": 0.0, "groundedness": 0.0}\n\n'
    "AFIRMACIÓN: {claim}"
)
_JUDGE_SCHEMA = {"faithfulness": 0.0, "groundedness": 0.0}


def _clamp(x: Any) -> Optional[float]:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return None


def judge_output(*, claim: str, evidence: List[Dict[str, Any]], provider=None) -> Optional[Dict[str, float]]:
    """Puntúa faithfulness/groundedness de una afirmación vs su evidencia. None si no hay LLM."""
    res = generate_structured(prompt=_JUDGE_PROMPT.format(claim=claim), context=evidence,
                              schema=_JUDGE_SCHEMA, provider=provider, on_failure="none")
    if res is None:
        return None
    f, g = _clamp(res.get("faithfulness")), _clamp(res.get("groundedness"))
    if f is None or g is None:
        return None
    return {"faithfulness": f, "groundedness": g}


def compute_ai_eval(*, verdicts: List[Dict[str, Any]], created_at: str, provider=None,
                    judge_model: str = "") -> Optional[Dict[str, Any]]:
    """Auto-evaluación de IA del run: juzga los veredictos llm_assisted. None si no hay
    ninguno o si el LLM no está disponible (degradación elegante)."""
    targets = [v for v in verdicts if v.get("llm_assisted")]
    if not targets:
        return None
    scores = []
    for v in targets:
        eb = v.get("evidence_bundle") or {}
        evidence = [{"id": k, "content": str(val)} for k, val in eb.items()] if isinstance(eb, dict) else []
        claim = f"categoría={v.get('category')} (regla {v.get('rule_applied')})"
        s = judge_output(claim=claim, evidence=evidence, provider=provider)
        if s is not None:
            scores.append(s)
    if not scores:
        return None   # el LLM no pudo juzgar ninguno → degrada
    n = len(scores)
    return {
        "method": "llm_judge",
        "judge_model": judge_model,
        "faithfulness": round(sum(s["faithfulness"] for s in scores) / n, 4),
        "groundedness": round(sum(s["groundedness"] for s in scores) / n, 4),
        "n": n,
        "evaluated_at": created_at,
    }
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m pytest tests/test_ai_judge.py -q`. Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 5: Commit**

```bash
git add src/ai/judge.py tests/test_ai_judge.py
git commit -m "feat(ai): LLM-judge (faithfulness/groundedness) + compute_ai_eval del run

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 3: Integrar `ai_eval` en el certificado (degrada el veredicto; firmado)

**Files:** Modify `src/certify/certificate.py` (`compute_self_eval`), `src/certify/service.py` (`generate` + provider); Test: extend `tests/test_certificate.py` + `tests/test_certify_service_selfeval.py`.

**Interfaces:** Consumes — `compute_ai_eval` (Task 2). Produces — `compute_self_eval(*, calibration, verdicts, created_at, ai_eval=None)` con el `ai_eval` en el dict y `confidence` forzado a `"low"` si `ai_eval.faithfulness < 0.5`.

- [ ] **Step 1: Write the failing tests** in `tests/test_certificate.py`:

```python
def test_self_eval_includes_ai_eval_and_low_faithfulness_forces_low_confidence():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}   # de por sí "high"
    ai = {"method": "llm_judge", "faithfulness": 0.3, "groundedness": 0.4, "n": 2, "evaluated_at": "t"}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": True}], created_at="t", ai_eval=ai)
    assert se["ai_eval"] == ai
    assert se["confidence"] == "low"   # IA poco fiel → degrada aunque la calibración sea alta

def test_self_eval_ai_eval_none_keeps_deterministic_confidence():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": False}], created_at="t", ai_eval=None)
    assert se["ai_eval"] is None and se["confidence"] == "high"   # #27 intacto

def test_high_faithfulness_does_not_inflate():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.0, "n_corrections": 0}   # cold-start → low
    ai = {"faithfulness": 0.99, "groundedness": 0.99, "n": 1}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": True}], created_at="t", ai_eval=ai)
    assert se["confidence"] == "low"   # la IA NUNCA infla; el cold-start manda
```

- [ ] **Step 2: Run, expect FAIL**.

- [ ] **Step 3: Implement** in `src/certify/certificate.py`. Add the constant and extend `compute_self_eval`:

```python
_LOW_FAITHFULNESS = 0.5
```

```python
def compute_self_eval(*, calibration: Dict[str, Any], verdicts: List[Dict[str, Any]],
                      created_at: str, ai_eval: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Auto-evaluación del motor (deterministic_v1) + ai_eval opcional del LLM-judge. Pura.
    ai_eval con faithfulness bajo DEGRADA confidence a 'low' (nunca lo infla)."""
    total = len(verdicts)
    llm_assisted = sum(1 for v in verdicts if v.get("llm_assisted"))
    confidence = compute_confidence(calibration)
    if ai_eval is not None and ai_eval.get("faithfulness", 1.0) < _LOW_FAITHFULNESS:
        confidence = "low"
    return {
        "method": "deterministic_v1",
        "engine_calibration": {
            "tenant_accuracy": calibration.get("tenant_accuracy", 0.0),
            "n_corrections": calibration.get("n_corrections", 0),
            "por_categoria_humana": calibration.get("por_categoria_humana", {}),
        },
        "run_composition": {"total": total, "deterministic": total - llm_assisted,
                            "llm_assisted": llm_assisted},
        "confidence": confidence,
        "ai_eval": ai_eval,
        "evaluated_at": created_at,
    }
```
(Add `Optional` to the `typing` import.)

- [ ] **Step 4: Wire the service.** In `src/certify/service.py`: `__init__` gains an optional `llm_provider=None`; `generate` computes `ai_eval` (degrading to `None` on any error) and passes it. Add the import `from src.ai.judge import compute_ai_eval`, store `self._llm_provider = llm_provider` in `__init__`, and between the `calibration = {...}` block and the `self_eval = compute_self_eval(...)` call:

```python
        try:
            ai_eval = compute_ai_eval(verdicts=verdicts, created_at=created_at,
                                      provider=self._llm_provider, judge_model=self._model_version)
        except Exception:  # noqa: BLE001 — el judge nunca rompe la emisión del certificado
            ai_eval = None
        self_eval = compute_self_eval(calibration=calibration, verdicts=verdicts,
                                      created_at=created_at, ai_eval=ai_eval)
```

- [ ] **Step 5: Run** — `python3 -m pytest tests/test_certificate.py tests/test_certify_service_selfeval.py -q` → PASS (the integration test from PR-1 still passes: a new tenant has no `llm_assisted` verdict → `ai_eval=None` → behaviour unchanged). Then `python3 -m pytest -m "not integration" -q` → green. The signature already covers `self_eval` (and thus `ai_eval`, nested) — no change needed in `signing.py`.

- [ ] **Step 6: Commit**

```bash
git add src/certify/certificate.py src/certify/service.py tests/test_certificate.py tests/test_certify_service_selfeval.py
git commit -m "feat(cert): ai_eval del LLM-judge firmado en el self_eval; faithfulness bajo degrada el veredicto

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Task 4: Medición — golden set de triaje + `scripts/eval_ai.py` + eval-en-CI

**Files:** Create `tests/golden/golden_triage.jsonl`, `scripts/eval_ai.py`; Modify `.github/workflows/backend-ci.yml`; Test `tests/test_eval_ai.py`.

**Interfaces:** Produces — `scripts/eval_ai.py` ejecutable (`python3 scripts/eval_ai.py [--min-accuracy 0.8]`) que corre el motor DETERMINISTA de triaje contra el golden y sale con código ≠0 si la precisión < umbral. Sin LLM (corre en CI).

- [ ] **Step 1: Read the triage engine signature.** Read `src/triage/engine.py` and `src/triage/signals.py` (or wherever the `Signals`/decision input is defined) to learn the exact decision function and the signal fields. The golden cases provide signal dicts; `eval_ai.py` builds the engine input from each and compares the decided category to `expected_category`. (Mirror how `tests/test_triage_engine*.py` constructs signals + calls the engine.)

- [ ] **Step 2: Write the golden set** — `tests/golden/golden_triage.jsonl` (one JSON object per line; ≥8 cases covering each category). Each line: `{"name": "...", "signals": {<fields the engine consumes>}, "expected_category": "flaky|infra|maintenance|real|unknown"}`. Derive the signal field names from Step 1 (e.g. `retried`, `intermittent`, `co_failure`, `locator_error`, `dom_changed`, `has_green_baseline`, `assertion_failure`, `novel`, `recurrent`, `family_label`). Include at least: a clear flaky (retry), an infra (co-failure), a maintenance (locator+dom_changed, no assertion), a real-recurrent (assertion+recurrent), a real-novel (assertion+novel).

- [ ] **Step 3: Write `scripts/eval_ai.py`:**

```python
"""Evalúa la precisión del motor DETERMINISTA de triaje contra el golden set.
Sin LLM (corre en CI). Sale con código !=0 si la precisión < umbral."""
import argparse
import json
import sys
from pathlib import Path

# Importa el motor y el constructor de señales según engine.py (ajustar al Step 1).
from src.triage.engine import decide_verdict      # <- nombre real del decisor (verificar en Step 1)
from src.triage.signals import Signals            # <- clase/estructura real (verificar en Step 1)

GOLDEN = Path(__file__).resolve().parent.parent / "tests" / "golden" / "golden_triage.jsonl"


def run(min_accuracy: float) -> int:
    cases = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    hits = 0
    for c in cases:
        signals = Signals(**c["signals"])          # ajustar a la firma real
        verdict = decide_verdict(signals)          # ajustar a la firma real
        got = verdict.category if hasattr(verdict, "category") else verdict["category"]
        if got == c["expected_category"]:
            hits += 1
    acc = hits / len(cases) if cases else 0.0
    print(f"triage golden: {hits}/{len(cases)} = {acc:.3f} (min {min_accuracy})")
    return 0 if acc >= min_accuracy else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-accuracy", type=float, default=0.8)
    sys.exit(run(ap.parse_args().min_accuracy))
```
(Adjust `decide_verdict`/`Signals` to the real names found in Step 1.)

- [ ] **Step 4: Write the test** — `tests/test_eval_ai.py`:

```python
import subprocess
import sys


def test_eval_ai_passes_on_golden():
    r = subprocess.run([sys.executable, "scripts/eval_ai.py", "--min-accuracy", "0.8"],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"eval falló: {r.stdout}\n{r.stderr}"
    assert "triage golden:" in r.stdout
```

- [ ] **Step 5: Run** — `python3 -m pytest tests/test_eval_ai.py -q` → PASS (the engine must score ≥0.8 on the golden; if a case is wrong, fix the golden case, not the engine). Then `python3 -m pytest -m "not integration" -q` → green.

- [ ] **Step 6: Wire CI.** In `.github/workflows/backend-ci.yml`, add a step after "Run unit tests":

```yaml
      - name: AI eval (golden de triaje)
        run: python -m scripts.eval_ai --min-accuracy 0.8
```
(If `python -m scripts.eval_ai` needs an `__init__.py` in `scripts/`, prefer `run: python scripts/eval_ai.py --min-accuracy 0.8`.)

- [ ] **Step 7: Commit**

```bash
git add tests/golden/golden_triage.jsonl scripts/eval_ai.py tests/test_eval_ai.py .github/workflows/backend-ci.yml
git commit -m "feat(eval): golden set de triaje + eval-en-CI (Mnemo se aplica su propia medicina)

Claude-Session: https://claude.ai/code/session_0198KfgRWvAM8BhiVz24uTok"
```

---

## Notas de cierre

- **`ai_eval` firmado:** va dentro de `self_eval`, que ya entra en `canonical_json` → firmado sin tocar `signing.py`. Un test de manipulación (flip `ai_eval.faithfulness` → firma falla) puede añadirse pero el de PR-1 ya prueba que el sobre cubre `self_eval`.
- **Degradación elegante e2e:** sin LLM → `compute_ai_eval` None → `self_eval.ai_eval` None → veredicto = el determinista de #27. PR-B1 no rompe nada si Ollama no está.
- **El eval-en-CI mide el MOTOR determinista** (sin LLM, factible en CI). El judge/RAGAS sobre salidas generativas se mide en runtime (en el cert) — su calidad real se valida cuando exista B2/B3 con LLM local.
- **Fuera de alcance:** B2 (causa-raíz, refactor de `structured_analyzer` al provider híbrido), B3 (NL), B4 (AST), B5 (orquestador).
