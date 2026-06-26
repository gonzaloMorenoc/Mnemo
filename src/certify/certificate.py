from typing import Any, Dict, List, Optional

_CATEGORIES = ("real", "flaky", "maintenance", "infra", "unknown")

_DISCLAIMER = (
    "Este certificado es un acta de evidencia reproducible: registra los fallos observados, "
    "la evaluación del motor de triaje (determinista, auditable) y las aprobaciones humanas. "
    "La 'evaluación' es una señal asistida, no una garantía de ausencia de defectos ni una "
    "certificación de aptitud legal."
)

# Umbrales de confianza del motor (spec Bloque A): cold-start y precisión por tenant.
_LOW_FAITHFULNESS = 0.5
_COLD_START_MIN_CORRECTIONS = 30
_LOW_ACCURACY = 0.60
_HIGH_MIN_CORRECTIONS = 100
_HIGH_MIN_ACCURACY = 0.80


def compute_confidence(calibration: Dict[str, Any]) -> str:
    """Confianza del motor en este tenant a partir de su calibración acumulada."""
    n = calibration.get("n_corrections", 0)
    acc = calibration.get("tenant_accuracy", 0.0)
    if n < _COLD_START_MIN_CORRECTIONS or acc < _LOW_ACCURACY:
        return "low"
    if n >= _HIGH_MIN_CORRECTIONS and acc >= _HIGH_MIN_ACCURACY:
        return "high"
    return "medium"


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


def compute_verdict(verdicts: List[Dict[str, Any]], confidence: str = "high") -> str:
    """Veredicto de aseguramiento (política §7.1) sobre los veredictos de triaje.
    Compartido por el certificado (F4a) y el gate (F4b)."""
    reales_novel_sin_approval = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") == "R5_real_novel" and not v.get("requires_approval"))
    pendientes_approval = sum(1 for v in verdicts if v.get("requires_approval"))
    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        return "no-apto"
    if any(v.get("category") in ("real", "maintenance") for v in verdicts):
        return "apto-con-reservas"
    if confidence == "low":
        return "apto-con-reservas"   # baja calibración del motor → no certificar apto rotundo
    return "apto"


def build_certificate(*, run: Dict[str, Any], verdicts: List[Dict[str, Any]],
                      sign_offs: List[Dict[str, Any]], mnemo_version: str,
                      model_version: str, created_at: str,
                      self_eval: Dict[str, Any]) -> Dict[str, Any]:
    """Certificado determinista de un run a partir de sus veredictos de triaje.
    Puro: el timestamp se inyecta (created_at). Schema v2: acta de evidencia con self_eval firmado."""
    breakdown = {c: 0 for c in _CATEGORIES}
    for v in verdicts:
        cat = v.get("category")
        if cat not in _CATEGORIES:
            cat = "unknown"
        breakdown[cat] += 1

    reales_novel_sin_approval = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") == "R5_real_novel" and not v.get("requires_approval"))
    pendientes_approval = sum(1 for v in verdicts if v.get("requires_approval"))
    reales_recurrentes = sum(
        1 for v in verdicts if v.get("category") == "real"
        and v.get("rule_applied") != "R5_real_novel")
    flaky = breakdown["flaky"]

    verdict = compute_verdict(verdicts, confidence=self_eval["confidence"])

    risk_score = min(100, 40 * reales_novel_sin_approval + 20 * pendientes_approval
                     + 10 * reales_recurrentes + 2 * flaky)

    evidence = [
        {"failure_id": v.get("failure_id"), "category": v.get("category"),
         "confidence": v.get("confidence"), "rule_applied": v.get("rule_applied"),
         "requires_approval": v.get("requires_approval")}
        for v in verdicts
    ]
    return {
        "schema": "mnemo.cert.v2",
        "attestation_type": "evidence_and_assessment",
        "disclaimer": _DISCLAIMER,
        "identity": {"org_id": run["org_id"], "project": run["project"],
                     "commit_sha": run.get("commit_sha"), "run_id": run["run_id"],
                     "created_at": created_at, "mnemo_version": mnemo_version,
                     "model_version": model_version},
        "verdict": verdict,
        "risk_score": risk_score,
        "breakdown": breakdown,
        "evidence": evidence,
        "sign_offs": sign_offs,
        "self_eval": self_eval,
    }
