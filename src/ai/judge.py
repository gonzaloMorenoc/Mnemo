from typing import Any, Dict, List, Optional

from src.ai.generate import generate_structured

_JUDGE_PROMPT = (
    "Eres un evaluador de calidad de QA. Dada una AFIRMACIÓN producida por un asistente y la "
    "EVIDENCIA disponible, puntúa de 0.0 a 1.0:\n"
    "- faithfulness: ¿la afirmación se sostiene SOLO en la evidencia, sin inventar?\n"
    "- groundedness: ¿está fundamentada en hechos concretos de la evidencia?\n"
    'Devuelve SOLO JSON: {{"faithfulness": 0.0, "groundedness": 0.0}}\n\n'
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
