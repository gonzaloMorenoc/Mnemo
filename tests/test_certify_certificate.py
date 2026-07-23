from src.certify.certificate import build_certificate, compute_self_eval, compute_verdict

_RUN = {"org_id": "o", "project": "web", "commit_sha": "abc123", "run_id": "r1"}
_HIGH_CALIBRATION = {"tenant_accuracy": 0.9, "n_corrections": 200}


def _v(category, *, rule="", approval=False, conf=0.9, fid="f1"):
    return {"id": "v", "failure_id": fid, "category": category, "confidence": conf,
            "rule_applied": rule, "evidence_bundle": {}, "requires_approval": approval,
            "llm_assisted": False, "status": "resolved"}


def _vv(category, *, rule="", approval=False):
    return {"failure_id": "f", "category": category, "confidence": 0.9,
            "rule_applied": rule, "requires_approval": approval}


# Un run limpio solo firma "apto" con un manifiesto de ejecución completo; estos
# tests preceden al manifiesto y asumen "verde→apto", así que se lo damos por defecto.
_COMPLETE_MANIFEST = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "complete": True}


def _cert(verdicts, manifest=_COMPLETE_MANIFEST):
    se = compute_self_eval(calibration=_HIGH_CALIBRATION, verdicts=verdicts,
                           created_at="2026-06-25T00:00:00Z")
    return build_certificate(run=_RUN, verdicts=verdicts, sign_offs=[],
                             mnemo_version="0.4.0", model_version="llama3",
                             created_at="2026-06-25T00:00:00Z", self_eval=se,
                             manifest=manifest)


def test_no_apto_on_novel_real_high_confidence():
    c = _cert([_v("real", rule="R5_real_novel", approval=False)])
    assert c["verdict"] == "no-apto"


def test_no_apto_on_pending_approval():
    c = _cert([_v("flaky", approval=True)])
    assert c["verdict"] == "no-apto"


def test_apto_con_reservas_on_recurrent_real():
    c = _cert([_v("real", rule="R4_real_recurrent", approval=False)])
    assert c["verdict"] == "apto-con-reservas"


def test_apto_when_all_flaky_or_infra():
    c = _cert([_v("flaky"), _v("infra")])
    assert c["verdict"] == "apto"


def test_breakdown_and_identity_and_evidence():
    c = _cert([_v("real", rule="R4_real_recurrent", fid="fa"), _v("flaky", fid="fb")])
    assert c["breakdown"]["real"] == 1 and c["breakdown"]["flaky"] == 1
    assert c["identity"]["commit_sha"] == "abc123" and c["identity"]["mnemo_version"] == "0.4.0"
    assert c["schema"] == "mnemo.cert.v3" and c["sign_offs"] == [] and c["self_eval"] is not None
    assert {e["failure_id"] for e in c["evidence"]} == {"fa", "fb"}


def test_risk_score_formula():
    # 1 novel-sin-approval (40) + 1 pendiente (20) + 1 recurrente (10) + 1 flaky (2) = 72
    c = _cert([_v("real", rule="R5_real_novel"), _v("infra", approval=True),
               _v("real", rule="R4_real_recurrent"), _v("flaky")])
    assert c["risk_score"] == 72
    assert c["verdict"] == "no-apto"  # hay novel-sin-approval y pendiente


def test_compute_verdict_no_apto_on_novel_real():
    assert compute_verdict([_vv("real", rule="R5_real_novel")]) == "no-apto"


def test_compute_verdict_no_apto_on_pending_approval():
    assert compute_verdict([_vv("flaky", approval=True)]) == "no-apto"


def test_compute_verdict_con_reservas_on_recurrent_real_or_maintenance():
    assert compute_verdict([_vv("real", rule="R4_real_recurrent")]) == "apto-con-reservas"
    assert compute_verdict([_vv("maintenance")]) == "apto-con-reservas"


def test_compute_verdict_apto_on_flaky_or_infra():
    assert compute_verdict([_vv("flaky"), _vv("infra")], manifest=_COMPLETE_MANIFEST) == "apto"


def test_compute_verdict_inconcluso_on_empty_without_manifest():
    # Sin manifiesto no se puede probar que corrieron tests → inconcluso (antes: "apto").
    assert compute_verdict([]) == "inconcluso"
    assert compute_verdict([], manifest=_COMPLETE_MANIFEST) == "apto"
