from dataclasses import dataclass

from src.triage.signals import Signals

_APPROVAL_THRESHOLD = 0.80


@dataclass
class TriageVerdict:
    category: str          # flaky | infra | maintenance | real | unknown
    confidence: float
    rule_applied: str
    requires_approval: bool
    llm_assisted: bool
    ambiguous: bool


def triage(signals: Signals) -> TriageVerdict:
    """Clasificación determinista por reglas de prioridad. El ambiguo (R6) queda
    'unknown' + ambiguous=True para que el desempate LLM (F2f) lo resuelva."""
    if signals.retry_passed_in_run or signals.intermittent_same_sha or signals.known_flaky_family:
        return _verdict("flaky", 0.90, "R1_flaky")
    if signals.mass_cofailure and signals.infra_error:
        return _verdict("infra", 0.90, "R2_infra")
    if signals.locator_error and signals.has_green_baseline and signals.dom_changed:
        return _verdict("maintenance", 0.80, "R3_maintenance")
    if signals.assertion_failure and signals.recurrent:
        return _verdict("real", 0.85, "R4_real_recurrent")
    if signals.assertion_failure and signals.novel:
        return _verdict("real", 0.75, "R5_real_novel", novel=True)
    return TriageVerdict(
        category="unknown", confidence=0.0, rule_applied="R6_ambiguous",
        requires_approval=True, llm_assisted=False, ambiguous=True,
    )


def _verdict(category: str, confidence: float, rule: str, *, novel: bool = False) -> TriageVerdict:
    requires_approval = confidence < _APPROVAL_THRESHOLD or (category == "real" and novel)
    return TriageVerdict(
        category=category, confidence=confidence, rule_applied=rule,
        requires_approval=requires_approval, llm_assisted=False, ambiguous=False,
    )
