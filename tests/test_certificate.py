from src.certify.certificate import build_certificate, compute_confidence, compute_self_eval, compute_verdict
from src.certify.signing import canonical_json, sign, verify
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def _keys():
    sk = Ed25519PrivateKey.generate()
    priv = sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    pub = sk.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


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


def test_build_certificate_is_v2_with_self_eval_and_disclaimer():
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se)
    assert cert["schema"] == "mnemo.cert.v2"
    assert cert["attestation_type"] == "evidence_and_assessment"
    assert "garantía" in cert["disclaimer"].lower()
    assert cert["self_eval"]["confidence"] == "high"
    assert cert["verdict"] == "apto"   # confidence high, todo flaky

def test_low_confidence_self_eval_downgrades_cert_verdict():
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.0, "n_corrections": 0},  # cold-start → low
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se)
    assert cert["verdict"] == "apto-con-reservas"

def test_signature_covers_self_eval():
    priv, pub = _keys()
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se)
    sig = sign(canonical_json(cert), priv)
    assert verify(canonical_json(cert), sig, pub) is True
    cert["self_eval"]["confidence"] = "low"   # tamper
    assert verify(canonical_json(cert), sig, pub) is False
