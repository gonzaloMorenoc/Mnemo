from typing import Any, Callable, Dict, List, Tuple

from src.certify.certificate import compute_confidence, compute_verdict

_CONCLUSION = {"no-apto": "failure", "apto-con-reservas": "neutral", "apto": "success",
               "sin_confirmar": "neutral"}
_CATEGORIES = ("real", "flaky", "maintenance", "infra", "unknown")
_MOTIVO = {
    "no-apto": "El motor evaluó: defecto real sin precedente de alta confianza o ítems pendientes de aprobación (Nivel 2).",
    "apto-con-reservas": "El motor evaluó: hay defectos reales recurrentes o mantenimiento; revisar antes de liberar.",
    "apto": "El motor evaluó: todo flaky en cuarentena, curado o infra reconocida.",
    "sin_confirmar": "No se pudo confirmar una ejecución completa (manifiesto ausente o incompleto).",
}


def _render_output(verdict: str, verdicts: List[Dict[str, Any]]) -> Tuple[str, str]:
    counts = {c: 0 for c in _CATEGORIES}
    for v in verdicts:
        cat = v.get("category")
        counts[cat if cat in _CATEGORIES else "unknown"] += 1
    desglose = ", ".join(f"{k}: {n}" for k, n in counts.items() if n) or "sin fallos"
    title = f"Mnemo Assurance: {verdict}"
    summary = (f"**Evaluación del motor:** {verdict}\n\n**Desglose:** {desglose}\n\n{_MOTIVO[verdict]}")
    return title, summary


class GateService:
    """Publica el check run mnemo/assurance del run según su veredicto (saliente)."""

    def __init__(self, *, repo, cert_repo, codehost_factory: Callable):
        self.repo = repo                       # AssuranceRepository (get_triage_for_run)
        self.cert_repo = cert_repo             # CertificateRepository (get_run_meta)
        self.codehost_factory = codehost_factory

    def publish(self, *, user_id: str, run_id: str) -> Dict[str, Any]:
        meta = self.cert_repo.get_run_meta(user_id=user_id, run_id=run_id)
        if meta is None:
            raise ValueError("run no encontrado o sin acceso")
        head_sha = meta.get("commit_sha")
        if not head_sha:
            raise ValueError("el run no tiene commit_sha; no se puede publicar el check run")
        verdicts = self.repo.get_triage_for_run(user_id=user_id, run_id=run_id)
        if not verdicts and self.repo.count_failures_for_run(user_id=user_id, run_id=run_id) > 0:
            # Run con fallos sin triar → no publicar gate. Un run verde (0 fallos)
            # sí publica un check "apto": es el caso central del gate.
            raise ValueError("run con fallos sin triar: ejecuta el triaje antes de publicar el gate")
        raw_cal = self.repo.get_calibration_metrics(user_id=user_id, org_id=meta["org_id"]) or {}
        confidence = compute_confidence({"tenant_accuracy": raw_cal.get("accuracy", 0.0),
                                         "n_corrections": raw_cal.get("total", 0)})
        verdict = compute_verdict(verdicts, confidence=confidence, manifest=meta.get("manifest"))
        conclusion = _CONCLUSION[verdict]
        title, summary = _render_output(verdict, verdicts)
        codehost = self.codehost_factory(meta["org_id"], user_id)
        url = codehost.publish_check_run(head_sha=head_sha, conclusion=conclusion,
                                         title=title, summary=summary)
        return {"verdict": verdict, "conclusion": conclusion, "check_run_url": url}
