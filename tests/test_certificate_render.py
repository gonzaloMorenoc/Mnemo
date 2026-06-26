from src.certify.render import render_html


def _cert(rule="R1"):
    return {"schema": "mnemo.cert.v2", "attestation_type": "evidence_and_assessment",
            "disclaimer": "… no es una garantía …", "verdict": "apto-con-reservas", "risk_score": 10,
            "identity": {"project": "p", "commit_sha": "s", "run_id": "r", "created_at": "t",
                         "mnemo_version": "1.0", "model_version": "x"},
            "breakdown": {"real": 1}, "self_eval": {"confidence": "low",
                "engine_calibration": {"tenant_accuracy": 0.0, "n_corrections": 0}},
            "evidence": [{"failure_id": "f1", "category": "real", "confidence": 0.75,
                          "rule_applied": rule, "requires_approval": True}], "sign_offs": []}


def test_render_shows_disclaimer_and_assessment_label():
    out = render_html(_cert(), "SIG")
    assert "no es una garantía" in out.lower() or "garantía" in out.lower()
    assert "Evaluación del motor" in out
    assert "Veredicto:</strong>" not in out   # ya no se rotula como dictamen

def test_render_shows_self_eval_confidence():
    out = render_html(_cert(), "SIG")
    assert "low" in out.lower() and ("confianza" in out.lower())

def test_render_renames_real_novel():
    out = render_html(_cert(rule="R5_real_novel"), "SIG")
    assert "real (sin precedente en el histórico)" in out
    assert "R5_real_novel" not in out   # no se muestra el id crudo de la regla
