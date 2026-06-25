from src.certify.certificate import build_certificate

_RUN = {"org_id": "o", "project": "web", "commit_sha": "abc123", "run_id": "r1"}


def _v(category, *, rule="", approval=False, conf=0.9, fid="f1"):
    return {"id": "v", "failure_id": fid, "category": category, "confidence": conf,
            "rule_applied": rule, "evidence_bundle": {}, "requires_approval": approval,
            "llm_assisted": False, "status": "resolved"}


def _cert(verdicts):
    return build_certificate(run=_RUN, verdicts=verdicts, sign_offs=[],
                             mnemo_version="0.4.0", model_version="llama3", created_at="2026-06-25T00:00:00Z")


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
    assert c["schema"] == "mnemo.cert.v1" and c["sign_offs"] == [] and c["self_eval"] is None
    assert {e["failure_id"] for e in c["evidence"]} == {"fa", "fb"}


def test_risk_score_formula():
    # 1 novel-sin-approval (40) + 1 pendiente (20) + 1 recurrente (10) + 1 flaky (2) = 72
    c = _cert([_v("real", rule="R5_real_novel"), _v("infra", approval=True),
               _v("real", rule="R4_real_recurrent"), _v("flaky")])
    assert c["risk_score"] == 72
    assert c["verdict"] == "no-apto"  # hay novel-sin-approval y pendiente
