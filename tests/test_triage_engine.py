from src.triage.engine import triage
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


def test_r1_flaky_by_retry():
    v = triage(_sig(retry_passed_in_run=True))
    assert v.category == "flaky" and v.confidence == 0.90 and v.rule_applied == "R1_flaky"
    assert v.requires_approval is False and v.ambiguous is False and v.llm_assisted is False


def test_r1_flaky_by_intermittency():
    assert triage(_sig(intermittent_same_sha=True)).category == "flaky"
    assert triage(_sig(intermittent_same_sha=True)).rule_applied == "R1_flaky"


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


def test_priority_r0_over_other_rules():
    v = triage(_sig(family_label="flaky", mass_cofailure=True, infra_error=True))
    assert v.category == "flaky" and v.rule_applied == "R0_calibrated"  # R0 antes que R2


def test_r0_calibrated_each_category():
    for cat in ("flaky", "real", "maintenance", "infra"):
        v = triage(_sig(family_label=cat))
        assert v.category == cat and v.rule_applied == "R0_calibrated"
        assert v.confidence == 0.95 and v.requires_approval is False
        assert v.llm_assisted is False and v.ambiguous is False


def test_r0_safety_net_yields_to_real_novel():
    # familia etiquetada flaky pero aserción + novedoso → posible bug real nuevo → R5, no R0
    v = triage(_sig(family_label="flaky", assertion_failure=True, novel=True))
    assert v.category == "real" and v.rule_applied == "R5_real_novel"


def test_r0_does_not_fire_on_unknown_label():
    # family_label='unknown' → R0 no aplica; cae en R1-R6 como antes
    assert triage(_sig(family_label="unknown", retry_passed_in_run=True)).rule_applied == "R1_flaky"
    assert triage(_sig(family_label="unknown", assertion_failure=True, novel=True)).rule_applied == "R5_real_novel"


def test_r0_recurrent_real_in_flaky_family_stays_calibrated():
    # aserción recurrente (no novel) en familia flaky → la red solo protege lo NOVEDOSO → R0 flaky
    v = triage(_sig(family_label="flaky", assertion_failure=True, recurrent=True))
    assert v.category == "flaky" and v.rule_applied == "R0_calibrated"


def test_priority_infra_over_maintenance():
    # mass_cofailure+infra_error (R2) y locator+baseline+dom_changed (R3) a la vez → infra (R2 antes que R3)
    v = triage(_sig(mass_cofailure=True, infra_error=True,
                    locator_error=True, has_green_baseline=True, dom_changed=True))
    assert v.category == "infra" and v.rule_applied == "R2_infra"


def test_assertion_with_locator_and_dom_change_is_real_not_maintenance():
    # un defecto real (aserción) con baseline verde + DOM cambiado NO es mantenimiento
    v = triage(_sig(locator_error=True, has_green_baseline=True, dom_changed=True,
                    assertion_failure=True, recurrent=True))
    assert v.category == "real" and v.rule_applied == "R4_real_recurrent"


def test_assertion_novel_with_locator_and_dom_change_is_real():
    v = triage(_sig(locator_error=True, has_green_baseline=True, dom_changed=True,
                    assertion_failure=True, novel=True))
    assert v.category == "real" and v.rule_applied == "R5_real_novel"
