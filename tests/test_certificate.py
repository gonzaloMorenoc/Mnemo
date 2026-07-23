from src.certify.certificate import build_certificate, compute_confidence, compute_self_eval, compute_verdict

# Un run limpio (solo flaky/infra) solo firma "apto" con manifiesto completo.
_M = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "complete": True}
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
    assert compute_verdict(apto, confidence="high", manifest=_M) == "apto"
    assert compute_verdict(apto, confidence="low", manifest=_M) == "apto-con-reservas"
    # no-apto y apto-con-reservas no cambian con confidence
    pend = [{"category": "real", "requires_approval": True}]
    assert compute_verdict(pend, confidence="low") == "no-apto"


def test_verdict_llm_assisted_never_yields_clean_apto():
    # D3: invariante ESTRUCTURAL — una categoría asistida por IA nunca produce un
    # "apto" rotundo, aunque un humano haya quitado requires_approval. Antes esto
    # colgaba solo de requires_approval=True; ahora compute_verdict lo garantiza.
    llm = [{"category": "flaky", "requires_approval": False, "llm_assisted": True}]
    assert compute_verdict(llm, confidence="high", manifest=_M) == "apto-con-reservas"
    # un run determinista equivalente (sin IA) sí puede ser apto
    det = [{"category": "flaky", "requires_approval": False, "llm_assisted": False}]
    assert compute_verdict(det, confidence="high", manifest=_M) == "apto"


def test_build_certificate_is_v2_with_self_eval_and_disclaimer():
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se, manifest=_M)
    assert cert["schema"] == "mnemo.cert.v3"
    assert cert["attestation_type"] == "evidence_and_assessment"
    assert "garantía" in cert["disclaimer"].lower()
    assert cert["self_eval"]["confidence"] == "high"
    assert cert["verdict"] == "apto"   # confidence high, todo flaky
    assert cert["identity"]["algorithm"] == "ed25519"   # D4: verificador sabe algoritmo
    assert cert["identity"]["key_id"] == ""             # sin key_id explícito → vacío


def test_key_id_is_deterministic_and_scoped():
    from src.certify.signing import key_id
    pem = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----"
    kid = key_id(pem)
    assert kid == key_id(pem) and len(kid) == 16          # determinista
    assert key_id(pem + "x") != kid                       # cambia con la clave
    assert key_id("") == ""                               # sin clave → vacío


def test_build_certificate_includes_key_id_when_provided():
    se = compute_self_eval(calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
                           verdicts=[], created_at="t")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=[], sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="t", self_eval=se, key_id="abc123")
    assert cert["identity"]["key_id"] == "abc123"
    assert cert["identity"]["algorithm"] == "ed25519"

def test_low_confidence_self_eval_downgrades_cert_verdict():
    verdicts = [{"category": "flaky", "requires_approval": False, "rule_applied": "R1", "llm_assisted": False,
                 "failure_id": "f1", "confidence": 0.9}]
    se = compute_self_eval(calibration={"tenant_accuracy": 0.0, "n_corrections": 0},  # cold-start → low
                           verdicts=verdicts, created_at="2026-06-26T00:00:00Z")
    cert = build_certificate(run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
                             verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
                             created_at="2026-06-26T00:00:00Z", self_eval=se, manifest=_M)
    assert cert["verdict"] == "apto-con-reservas"

def test_self_eval_includes_ai_eval_but_does_not_modulate_confidence():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}   # determinista: "high"
    ai = {"method": "llm_judge", "faithfulness": 0.3, "groundedness": 0.4, "n": 2, "evaluated_at": "t"}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": True}], created_at="t", ai_eval=ai)
    assert se["ai_eval"] == ai                 # ai_eval sigue presente (informativo, firmado)
    assert se["confidence"] == "high"          # NO lo degrada: el confidence es el determinista


def test_verdict_identical_with_and_without_ai_eval():
    from src.certify.certificate import compute_self_eval, compute_verdict
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}        # "high"
    verdicts = [{"category": "flaky", "llm_assisted": True}]    # llm_assisted → apto-con-reservas (D3)
    se_none = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="t", ai_eval=None)
    ai_bad = {"faithfulness": 0.1, "groundedness": 0.1, "n": 1}
    se_ai = compute_self_eval(calibration=cal, verdicts=verdicts, created_at="t", ai_eval=ai_bad)
    assert se_none["confidence"] == se_ai["confidence"] == "high"        # ai_eval no modula
    v_none = compute_verdict(verdicts, confidence=se_none["confidence"], manifest=_M)
    v_ai = compute_verdict(verdicts, confidence=se_ai["confidence"], manifest=_M)
    # ai_eval no cambia el veredicto (reproducible); es apto-con-reservas por ser llm_assisted (D3)
    assert v_none == v_ai == "apto-con-reservas"

def test_self_eval_ai_eval_none_keeps_deterministic_confidence():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.9, "n_corrections": 200}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": False}], created_at="t", ai_eval=None)
    assert se["ai_eval"] is None and se["confidence"] == "high"   # #27 intacto

def test_high_faithfulness_does_not_inflate():
    from src.certify.certificate import compute_self_eval
    cal = {"tenant_accuracy": 0.0, "n_corrections": 0}   # cold-start → low
    ai = {"faithfulness": 0.99, "groundedness": 0.99, "n": 1}
    se = compute_self_eval(calibration=cal, verdicts=[{"llm_assisted": True}], created_at="t", ai_eval=ai)
    assert se["confidence"] == "low"   # la IA NUNCA infla; el cold-start manda


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


def test_signature_covers_ai_eval():
    """Mutating ai_eval inside self_eval must invalidate the signature."""
    priv, pub = _keys()
    verdicts = [{"category": "real", "requires_approval": False, "rule_applied": "R6_ambiguous",
                 "llm_assisted": True, "failure_id": "f1", "confidence": 0.9}]
    ai_eval = {
        "method": "llm_judge",
        "faithfulness": 0.9,
        "groundedness": 0.9,
        "n": 1,
        "evaluated_at": "t",
    }
    se = compute_self_eval(
        calibration={"tenant_accuracy": 0.9, "n_corrections": 200},
        verdicts=verdicts,
        created_at="2026-06-26T00:00:00Z",
        ai_eval=ai_eval,
    )
    cert = build_certificate(
        run={"org_id": "o", "project": "p", "commit_sha": "s", "run_id": "r"},
        verdicts=verdicts, sign_offs=[], mnemo_version="1.0", model_version="x",
        created_at="2026-06-26T00:00:00Z", self_eval=se,
    )
    sig = sign(canonical_json(cert), priv)
    assert verify(canonical_json(cert), sig, pub) is True
    cert["self_eval"]["ai_eval"]["faithfulness"] = 0.1   # tamper
    assert verify(canonical_json(cert), sig, pub) is False
