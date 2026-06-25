from src.triage.signals import FailureInput, compute_signals


def _fi(**over):
    base = dict(
        error_type="TimeoutError", message="waiting for locator",
        is_novel=True, family_label="unknown", retry_passed_in_run=False,
        intermittent_same_sha=False, mass_cofailure=False,
        has_green_baseline=False, dom_changed=False,
    )
    base.update(over)
    return FailureInput(**base)


def test_classification_signals_from_message():
    s = compute_signals(_fi(message="locator not found"))
    assert s.locator_error is True and s.infra_error is False and s.assertion_failure is False


def test_family_label_passed_through():
    assert compute_signals(_fi(family_label="flaky")).family_label == "flaky"
    assert compute_signals(_fi(family_label="real")).family_label == "real"
    assert compute_signals(_fi(family_label="unknown")).family_label == "unknown"


def test_novel_and_recurrent_are_complementary():
    assert compute_signals(_fi(is_novel=True)).novel is True
    assert compute_signals(_fi(is_novel=True)).recurrent is False
    assert compute_signals(_fi(is_novel=False)).recurrent is True


def test_facts_passed_through():
    s = compute_signals(_fi(retry_passed_in_run=True, intermittent_same_sha=True,
                            mass_cofailure=True, has_green_baseline=True, dom_changed=True))
    assert s.retry_passed_in_run and s.intermittent_same_sha and s.mass_cofailure
    assert s.has_green_baseline and s.dom_changed


def test_trace_feeds_classification():
    s = compute_signals(_fi(message="test failed", trace="waiting for getByRole('btn')"))
    assert s.locator_error is True
