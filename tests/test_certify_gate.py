from unittest.mock import MagicMock

import pytest

from src.certify.gate import GateService


def _service(*, meta, verdicts, codehost=None, calibration=None, n_failures=0):
    repo = MagicMock()
    repo.get_triage_for_run.return_value = verdicts
    repo.count_failures_for_run.return_value = n_failures
    repo.get_calibration_metrics.return_value = calibration  # None → or {} → confidence "low"
    cert_repo = MagicMock()
    cert_repo.get_run_meta.return_value = meta
    codehost = codehost or MagicMock()
    codehost.publish_check_run.return_value = "https://github.com/o/r/runs/1"
    factory = MagicMock(return_value=codehost)
    svc = GateService(repo=repo, cert_repo=cert_repo, codehost_factory=factory)
    return svc, codehost, factory


# manifiesto completo por defecto → un run verde firma "apto" (los tests preceden al manifiesto)
_META = {"org_id": "o1", "project": "web", "commit_sha": "sha9",
         "manifest": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "complete": True}}


def _v(category, *, rule="", approval=False):
    return {"failure_id": "f", "category": category, "rule_applied": rule,
            "requires_approval": approval, "confidence": 0.9}


def test_publish_failure_for_novel_real():
    svc, codehost, _ = _service(meta=_META, verdicts=[_v("real", rule="R5_real_novel")])
    out = svc.publish(user_id="u", run_id="r")
    assert out["verdict"] == "no-apto" and out["conclusion"] == "failure"
    assert out["check_run_url"] == "https://github.com/o/r/runs/1"
    kwargs = codehost.publish_check_run.call_args.kwargs
    assert kwargs["head_sha"] == "sha9" and kwargs["conclusion"] == "failure"


def test_publish_neutral_for_recurrent_real():
    svc, _, _ = _service(meta=_META, verdicts=[_v("real", rule="R4_real_recurrent")])
    assert svc.publish(user_id="u", run_id="r")["conclusion"] == "neutral"


def test_publish_success_for_flaky():
    # calibración alta para que confidence == "high" y verdicts solo flaky → "apto"
    cal = {"accuracy": 0.85, "total": 150, "por_categoria": {}}
    svc, _, _ = _service(meta=_META, verdicts=[_v("flaky")], calibration=cal)
    assert svc.publish(user_id="u", run_id="r")["conclusion"] == "success"


def test_publish_raises_without_commit_sha():
    svc, _, _ = _service(meta={"org_id": "o1", "project": "web", "commit_sha": None},
                         verdicts=[_v("flaky")])
    with pytest.raises(ValueError):
        svc.publish(user_id="u", run_id="r")


def test_publish_raises_when_failures_untriaged():
    # Fallos ingeridos pero sin veredictos = run sin triar → no publicar gate.
    svc, _, _ = _service(meta=_META, verdicts=[], n_failures=3)
    with pytest.raises(ValueError):
        svc.publish(user_id="u", run_id="r")


def test_publish_green_run_is_success():
    # D2: run VERDE (0 fallos, 0 veredictos) → gate "apto"/success (caso central).
    cal = {"accuracy": 0.85, "total": 150, "por_categoria": {}}
    svc, codehost, _ = _service(meta=_META, verdicts=[], n_failures=0, calibration=cal)
    out = svc.publish(user_id="u", run_id="r")
    assert out["verdict"] == "apto" and out["conclusion"] == "success"
    assert codehost.publish_check_run.called


def test_publish_raises_when_run_not_found():
    svc, _, _ = _service(meta=None, verdicts=[_v("flaky")])
    with pytest.raises(ValueError):
        svc.publish(user_id="u", run_id="r")


def test_gate_dicts_aceptan_sin_confirmar_sin_keyerror():
    from src.certify.gate import _CONCLUSION, _MOTIVO, _render_output  # noqa: F401
    assert _CONCLUSION["sin_confirmar"] == "neutral"
    # _render_output indexa _MOTIVO[verdict] → no debe lanzar KeyError
    title, summary = _render_output("sin_confirmar", [])
    assert "sin_confirmar" in title
    assert "No se pudo confirmar" in summary
