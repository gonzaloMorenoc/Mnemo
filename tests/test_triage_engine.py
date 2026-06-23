from src.triage.engine import triage
from src.triage.signals import Signals


def _sig(**over):
    base = dict(
        infra_error=False, locator_error=False, assertion_failure=False,
        retry_passed_in_run=False, intermittent_same_sha=False, known_flaky_family=False,
        mass_cofailure=False, has_green_baseline=False, dom_changed=False,
        novel=False, recurrent=False,
    )
    base.update(over)
    return Signals(**base)


def test_r1_flaky_by_retry():
    v = triage(_sig(retry_passed_in_run=True))
    assert v.category == "flaky" and v.confidence == 0.90 and v.rule_applied == "R1_flaky"
    assert v.requires_approval is False and v.ambiguous is False and v.llm_assisted is False


def test_r1_flaky_by_intermittency_or_known_family():
    assert triage(_sig(intermittent_same_sha=True)).category == "flaky"
    assert triage(_sig(known_flaky_family=True)).category == "flaky"


def test_r2_infra_requires_mass_cofailure_and_infra_error():
    assert triage(_sig(mass_cofailure=True, infra_error=True)).category == "infra"
    assert triage(_sig(infra_error=True)).category != "infra"  # infra solo, sin co-fallo masivo


def test_r3_maintenance_requires_locator_baseline_dom_changed():
    v = triage(_sig(locator_error=True, has_green_baseline=True, dom_changed=True))
    assert v.category == "maintenance" and v.confidence == 0.80 and v.rule_applied == "R3_maintenance"
    assert v.requires_approval is False  # 0.80 NO es < 0.80
    # sin dom_changed → no es mantenimiento → ambiguo
    assert triage(_sig(locator_error=True, has_green_baseline=True)).category == "unknown"


def test_r4_real_recurrent():
    v = triage(_sig(assertion_failure=True, recurrent=True))
    assert v.category == "real" and v.confidence == 0.85 and v.requires_approval is False
    assert v.rule_applied == "R4_real_recurrent" and v.llm_assisted is False and v.ambiguous is False


def test_r5_real_novel_requires_approval():
    v = triage(_sig(assertion_failure=True, novel=True))
    assert v.category == "real" and v.confidence == 0.75 and v.requires_approval is True
    assert v.rule_applied == "R5_real_novel" and v.llm_assisted is False and v.ambiguous is False


def test_r6_ambiguous_unknown():
    v = triage(_sig(locator_error=True))  # locator sin baseline/dom_changed
    assert v.category == "unknown" and v.confidence == 0.0
    assert v.ambiguous is True and v.requires_approval is True
    assert v.rule_applied == "R6_ambiguous" and v.llm_assisted is False


def test_priority_flaky_over_infra():
    v = triage(_sig(known_flaky_family=True, mass_cofailure=True, infra_error=True))
    assert v.category == "flaky"  # R1 antes que R2


def test_priority_infra_over_maintenance():
    # mass_cofailure+infra_error (R2) y locator+baseline+dom_changed (R3) a la vez → infra (R2 antes que R3)
    v = triage(_sig(mass_cofailure=True, infra_error=True,
                    locator_error=True, has_green_baseline=True, dom_changed=True))
    assert v.category == "infra" and v.rule_applied == "R2_infra"
