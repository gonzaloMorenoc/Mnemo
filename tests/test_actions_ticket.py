from unittest.mock import MagicMock

from src.actions.ticket import TicketActuator


def _verdict(**over):
    # rule_applied vive DENTRO de evidence_bundle (es lo que devuelve get_run_actionable_verdicts),
    # no en el top-level del veredicto.
    base = {"verdict_id": "v1", "category": "real", "confidence": 0.85,
            "evidence_bundle": {"family_id": "fam-1", "rule_applied": "R4_real_recurrent",
                                "lineage_projects": ["web", "admin"]}}
    base.update(over)
    return base


def _ctx(root_cause=None):
    return {"test_name": "t_checkout",
            "family": {"title": "TimeoutError", "occurrence_count": 3, "root_cause": root_cause},
            "failures": [{"test_name": "t_checkout", "error_type": "TimeoutError",
                          "message": "boom", "trace": None, "project": "web"}]}


def test_ticket_uses_analyzer_when_no_stored_root_cause():
    analyzer = MagicMock()
    analyzer.analyze.return_value = "## Causa raíz\nProbable regresión."
    p = TicketActuator(analyzer).propose(_verdict(), _ctx())
    assert p.kind == "ticket"
    analyzer.analyze.assert_called_once()
    assert "Probable regresión" in p.payload["body"]
    assert "web, admin" in p.payload["body"]            # linaje


def test_ticket_prefers_stored_root_cause_no_llm_call():
    analyzer = MagicMock()
    p = TicketActuator(analyzer).propose(_verdict(), _ctx(root_cause="Ya analizado."))
    analyzer.analyze.assert_not_called()
    assert "Ya analizado." in p.payload["body"]


def test_ticket_degrades_when_analyzer_raises():
    analyzer = MagicMock()
    analyzer.analyze.side_effect = RuntimeError("LLM caído")
    p = TicketActuator(analyzer).propose(_verdict(), _ctx())
    assert "no disponible" in p.payload["body"].lower()
    assert p.kind == "ticket"


def test_ticket_no_failures_skips_analyzer_and_degrades():
    analyzer = MagicMock()
    ctx = {"test_name": "t_x", "family": {"title": "F", "root_cause": None}, "failures": []}
    p = TicketActuator(analyzer).propose(_verdict(), ctx)
    analyzer.analyze.assert_not_called()          # sin datos, no se llama al LLM
    assert "no disponible" in p.payload["body"].lower()
    assert p.kind == "ticket"


def test_ticket_includes_rule_from_evidence_bundle():
    # regresión: la regla se lee de evidence_bundle, no del top-level (antes salía "regla None")
    p = TicketActuator(MagicMock()).propose(_verdict(), _ctx(root_cause="ya"))
    assert "R4_real_recurrent" in p.payload["body"]
    assert "regla None" not in p.payload["body"]


def test_ticket_rule_degrades_when_absent():
    v = _verdict(evidence_bundle={"family_id": "fam-1", "lineage_projects": []})
    p = TicketActuator(MagicMock()).propose(v, _ctx(root_cause="ya"))
    assert "regla desconocida" in p.payload["body"]
