from src.certify.certificate import compute_confidence, compute_self_eval, compute_verdict


def test_confidence_low_on_cold_start():
    assert compute_confidence({"tenant_accuracy": 0.99, "n_corrections": 5}) == "low"   # n<30
    assert compute_confidence({"tenant_accuracy": 0.50, "n_corrections": 500}) == "low"  # acc<0.60

def test_confidence_high_and_medium():
    assert compute_confidence({"tenant_accuracy": 0.85, "n_corrections": 120}) == "high"
    assert compute_confidence({"tenant_accuracy": 0.85, "n_corrections": 50}) == "medium"  # n entre 30 y 100

def test_self_eval_shape_and_run_composition():
    verdicts = [{"llm_assisted": True}, {"llm_assisted": False}, {"llm_assisted": False}]
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200, "por_categoria_humana": {"real": 10}}
    se = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    assert se["method"] == "deterministic_v1"
    assert se["engine_calibration"] == {"tenant_accuracy": 0.9, "n_corrections": 200, "por_categoria_humana": {"real": 10}}
    assert se["run_composition"] == {"total": 3, "deterministic": 2, "llm_assisted": 1}
    assert se["confidence"] == "high" and se["evaluated_at"] == "2026-06-26T00:00:00Z"

def test_verdict_low_confidence_downgrades_apto_only():
    apto = [{"category": "flaky", "requires_approval": False}]
    assert compute_verdict(apto, confidence="high") == "apto"
    assert compute_verdict(apto, confidence="low") == "apto-con-reservas"
    # no-apto y apto-con-reservas no cambian con confidence
    pend = [{"category": "real", "requires_approval": True}]
    assert compute_verdict(pend, confidence="low") == "no-apto"
