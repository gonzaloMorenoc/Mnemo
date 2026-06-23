from typing import Any, Dict

from src.config import TRIAGE_MASS_COFAILURE_MIN
from src.triage.engine import triage
from src.triage.evidence import build_evidence
from src.triage.patterns import classify_error
from src.triage.signals import FailureInput, compute_signals

_CATEGORIES = ("flaky", "infra", "maintenance", "real", "unknown")


class TriageService:
    """Orquesta el triaje de un run: carga los hechos (repo), calcula mass_cofailure
    a nivel de run, clasifica cada fallo con el motor determinista y persiste los
    veredictos. Los ambiguos quedan 'needs_tiebreak' (el desempate LLM es F2f)."""

    def __init__(self, *, repo, threshold: int = TRIAGE_MASS_COFAILURE_MIN):
        self.repo = repo
        self.threshold = threshold

    def triage_run(self, *, user_id: str, run_id: str) -> Dict[str, int]:
        data = self.repo.get_triage_inputs(user_id=user_id, run_id=run_id)
        if data["run"] is None:
            return {}
        failures = data["failures"]

        infra_count = sum(
            1 for f in failures
            if "infra" in classify_error(f["error_type"], f["message"], f["trace"])
        )
        mass = infra_count >= self.threshold

        counts = {c: 0 for c in _CATEGORIES}
        verdicts = []
        for f in failures:
            signals = compute_signals(FailureInput(
                error_type=f["error_type"], message=f["message"], trace=f["trace"],
                is_novel=f["is_novel"], family_label=f["family_label"],
                retry_passed_in_run=f["retry_passed_in_run"],
                intermittent_same_sha=f["intermittent_same_sha"],
                mass_cofailure=mass,
                has_green_baseline=f["has_green_baseline"], dom_changed=f["dom_changed"],
            ))
            verdict = triage(signals)
            evidence = build_evidence(
                fingerprint=f["fingerprint"], family_id=f["family_id"],
                lineage_projects=f["lineage_projects"], error_type=f["error_type"],
                signals=signals, verdict=verdict,
            )
            verdicts.append({
                "failure_id": f["failure_id"],
                "category": verdict.category,
                "confidence": verdict.confidence,
                "rule_applied": verdict.rule_applied,
                "evidence_bundle": evidence,
                "requires_approval": verdict.requires_approval,
                "llm_assisted": verdict.llm_assisted,
                "status": "needs_tiebreak" if verdict.ambiguous else "resolved",
            })
            counts[verdict.category] = counts.get(verdict.category, 0) + 1

        self.repo.save_triage_verdicts(
            user_id=user_id, org_id=data["run"]["org_id"], run_id=run_id, verdicts=verdicts,
        )
        return counts
