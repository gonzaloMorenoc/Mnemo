from typing import Any, Dict, List

_CATEGORIES = ("real", "flaky", "maintenance", "infra", "unknown")


def build_certificate(*, run: Dict[str, Any], verdicts: List[Dict[str, Any]],
                      sign_offs: List[Dict[str, Any]], mnemo_version: str,
                      model_version: str, created_at: str) -> Dict[str, Any]:
    """Certificado determinista de un run a partir de sus veredictos de triaje.
    Puro: el timestamp se inyecta (created_at)."""
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

    if reales_novel_sin_approval > 0 or pendientes_approval > 0:
        verdict = "no-apto"
    elif breakdown["real"] > 0 or breakdown["maintenance"] > 0:
        verdict = "apto-con-reservas"
    else:
        verdict = "apto"

    risk_score = min(100, 40 * reales_novel_sin_approval + 20 * pendientes_approval
                     + 10 * reales_recurrentes + 2 * flaky)

    evidence = [
        {"failure_id": v.get("failure_id"), "category": v.get("category"),
         "confidence": v.get("confidence"), "rule_applied": v.get("rule_applied"),
         "requires_approval": v.get("requires_approval")}
        for v in verdicts
    ]
    return {
        "schema": "mnemo.cert.v1",
        "identity": {"org_id": run["org_id"], "project": run["project"],
                     "commit_sha": run.get("commit_sha"), "run_id": run["run_id"],
                     "created_at": created_at, "mnemo_version": mnemo_version,
                     "model_version": model_version},
        "verdict": verdict,
        "risk_score": risk_score,
        "breakdown": breakdown,
        "evidence": evidence,
        "sign_offs": sign_offs,
        "self_eval": None,
    }
