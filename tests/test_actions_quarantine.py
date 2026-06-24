from src.actions.quarantine import QuarantineActuator


def _verdict(**over):
    base = {"verdict_id": "v1", "category": "flaky", "confidence": 0.9,
            "evidence_bundle": {"family_id": "fam-1"}}
    base.update(over)
    return base


def test_quarantine_always_has_non_empty_debt_ticket():
    p = QuarantineActuator().propose(_verdict(), {"test_name": "t_login"})
    assert p.kind == "quarantine"
    dt = p.payload["debt_ticket"]
    assert dt["title"] and dt["body"]            # invariante: nunca vacío
    assert "t_login" in dt["title"] or "t_login" in dt["body"]


def test_quarantine_includes_annotation_with_test_name():
    p = QuarantineActuator().propose(_verdict(), {"test_name": "t_login"})
    assert p.payload["annotation"]["test_name"] == "t_login"
    assert "t_login" in p.summary


def test_quarantine_handles_missing_test_name():
    p = QuarantineActuator().propose(_verdict(), {})
    assert p.payload["debt_ticket"]["title"]     # sigue produciendo ticket de deuda
    assert p.payload["debt_ticket"]["body"]
    assert p.payload["annotation"]["test_name"] == "(test desconocido)"
