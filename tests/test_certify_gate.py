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


# ── memoria del equipo en el check run (presentación; el veredicto no cambia) ──
from src.memory import visibility  # noqa: E402
from src.memory.family_memory import FamilyMemory  # noqa: E402


@pytest.fixture(autouse=True)
def _no_visibility_cache():
    visibility.clear_cache()
    yield
    visibility.clear_cache()

_MEM = FamilyMemory(family_id="fam1", title="TimeoutError", label="infra",
                    reason="El sandbox del PSP se cae los lunes", reason_by="María")


def _with_family(v, fid="fam1"):
    return {**v, "evidence_bundle": {"family_id": fid}}


def _gate_with_memory(*, private, memories=(_MEM,), memory_error=None):
    codehost = MagicMock()
    codehost.repo_is_private.return_value = private
    svc, codehost, _ = _service(meta=_META, verdicts=[_with_family(_v("real", rule="R5_real_novel")),
                                                      _with_family(_v("real", rule="R5_real_novel"))],
                                codehost=codehost)
    memory_fn = MagicMock(return_value=list(memories), side_effect=memory_error)
    svc.memory_fn = memory_fn
    svc.app_url = "https://mnemo.example"
    return svc, codehost, memory_fn


def test_repo_privado_lleva_la_memoria_en_el_check():
    svc, codehost, memory_fn = _gate_with_memory(private=True)
    out = svc.publish(user_id="u", run_id="r")
    summary = codehost.publish_check_run.call_args.kwargs["summary"]
    assert "### Lo que Mnemo recuerda" in summary
    assert "El sandbox del PSP se cae los lunes" in summary
    assert memory_fn.call_args.kwargs == {"user_id": "u", "org_id": "o1", "family_ids": ["fam1"]}
    assert out["conclusion"] == "failure"          # el veredicto no depende de la memoria


def test_repo_publico_solo_enlaza_sin_detalle():
    svc, codehost, _ = _gate_with_memory(private=False)
    svc.publish(user_id="u", run_id="r")
    summary = codehost.publish_check_run.call_args.kwargs["summary"]
    assert "El sandbox" not in summary
    assert "memoria del equipo sobre 1 familia" in summary
    assert "https://mnemo.example/app/defects" in summary


def test_sin_memoria_el_check_no_cambia():
    svc, codehost, _ = _gate_with_memory(private=True, memories=(FamilyMemory("fam1", "x"),))
    svc.publish(user_id="u", run_id="r")
    assert "Mnemo recuerda" not in codehost.publish_check_run.call_args.kwargs["summary"]


def test_un_fallo_de_la_memoria_no_tumba_el_gate():
    svc, codehost, _ = _gate_with_memory(private=True, memory_error=RuntimeError("bd"))
    out = svc.publish(user_id="u", run_id="r")
    assert out["conclusion"] == "failure"
    assert "Mnemo recuerda" not in codehost.publish_check_run.call_args.kwargs["summary"]


def test_sin_memory_fn_se_comporta_como_antes():
    svc, codehost, _ = _service(meta=_META, verdicts=[_with_family(_v("real", rule="R5_real_novel"))])
    svc.publish(user_id="u", run_id="r")
    assert "Mnemo recuerda" not in codehost.publish_check_run.call_args.kwargs["summary"]
