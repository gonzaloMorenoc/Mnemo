from typing import Any, Callable, Dict, List, Tuple

from src.certify.certificate import compute_verdict

_CONCLUSION = {"no-apto": "failure", "apto-con-reservas": "neutral", "apto": "success"}
_CATEGORIES = ("real", "flaky", "maintenance", "infra", "unknown")
_MOTIVO = {
    "no-apto": "Defecto real novedoso de alta confianza o ítems pendientes de aprobación (Nivel 2).",
    "apto-con-reservas": "Hay defectos reales recurrentes o mantenimiento; revisar antes de liberar.",
    "apto": "Todo flaky en cuarentena, curado o infra reconocida.",
}


def _render_output(verdict: str, verdicts: List[Dict[str, Any]]) -> Tuple[str, str]:
    counts = {c: 0 for c in _CATEGORIES}
    for v in verdicts:
        cat = v.get("category")
        counts[cat if cat in _CATEGORIES else "unknown"] += 1
    desglose = ", ".join(f"{k}: {n}" for k, n in counts.items() if n) or "sin fallos"
    title = f"Mnemo Assurance: {verdict}"
    summary = (f"**Veredicto:** {verdict}\n\n**Desglose:** {desglose}\n\n{_MOTIVO[verdict]}")
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
        if not verdicts:
            raise ValueError("run sin veredictos de triaje")
        verdict = compute_verdict(verdicts)
        conclusion = _CONCLUSION[verdict]
        title, summary = _render_output(verdict, verdicts)
        codehost = self.codehost_factory(meta["org_id"], user_id)
        url = codehost.publish_check_run(head_sha=head_sha, conclusion=conclusion,
                                         title=title, summary=summary)
        return {"verdict": verdict, "conclusion": conclusion, "check_run_url": url}
