from typing import Any, Dict, List, Optional

from src.triage.engine import TriageVerdict
from src.triage.signals import Signals


def build_evidence(
    *,
    fingerprint: str,
    family_id: Optional[str],
    lineage_projects: List[str],
    error_type: Optional[str],
    signals: Signals,
    verdict: TriageVerdict,
) -> Dict[str, Any]:
    """Bundle auditable: el 'por qué' de la clasificación. Es lo que firmará el
    certificado (F4) y lo que un auditor lee para entender la decisión."""
    return {
        "fingerprint": fingerprint,
        "family_id": family_id,
        "lineage_projects": list(lineage_projects),
        "error_type": error_type,
        "signals": [{"name": name, "value": value} for name, value in _signal_items(signals)],
        "rule_applied": verdict.rule_applied,
        "category": verdict.category,
        "confidence": verdict.confidence,
        "requires_approval": verdict.requires_approval,
        "llm_assisted": verdict.llm_assisted,
    }


def _signal_items(signals: Signals):
    return [
        ("infra_error", signals.infra_error),
        ("locator_error", signals.locator_error),
        ("assertion_failure", signals.assertion_failure),
        ("retry_passed_in_run", signals.retry_passed_in_run),
        ("intermittent_same_sha", signals.intermittent_same_sha),
        ("known_flaky_family", signals.known_flaky_family),
        ("mass_cofailure", signals.mass_cofailure),
        ("has_green_baseline", signals.has_green_baseline),
        ("dom_changed", signals.dom_changed),
        ("novel", signals.novel),
        ("recurrent", signals.recurrent),
    ]
