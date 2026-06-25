from src.triage.engine import triage
from src.triage.evidence import build_evidence
from src.triage.signals import Signals


def _sig(**over):
    base = dict(
        infra_error=False, locator_error=False, assertion_failure=False,
        retry_passed_in_run=False, intermittent_same_sha=False, family_label="unknown",
        mass_cofailure=False, has_green_baseline=False, dom_changed=False,
        novel=False, recurrent=False,
    )
    base.update(over)
    return Signals(**base)


def test_evidence_bundle_shape():
    signals = _sig(locator_error=True, has_green_baseline=True, dom_changed=True)
    verdict = triage(signals)
    ev = build_evidence(
        fingerprint="fp1", family_id="fam1", lineage_projects=["proj-a", "proj-b"],
        error_type="TimeoutError", signals=signals, verdict=verdict,
    )
    assert ev["fingerprint"] == "fp1" and ev["family_id"] == "fam1"
    assert ev["lineage_projects"] == ["proj-a", "proj-b"]
    assert ev["error_type"] == "TimeoutError"
    assert ev["rule_applied"] == "R3_maintenance" and ev["category"] == "maintenance"
    assert ev["confidence"] == 0.80 and ev["requires_approval"] is False
    assert ev["llm_assisted"] is False
    names = {s["name"]: s["value"] for s in ev["signals"]}
    assert names["locator_error"] is True and names["dom_changed"] is True
    assert names["infra_error"] is False


def test_evidence_lists_all_signals():
    signals = _sig()
    ev = build_evidence(fingerprint="f", family_id=None, lineage_projects=[],
                        error_type=None, signals=signals, verdict=triage(signals))
    assert len(ev["signals"]) == 11
    assert ev["family_id"] is None and ev["error_type"] is None
