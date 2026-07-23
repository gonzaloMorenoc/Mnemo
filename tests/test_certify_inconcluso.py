from src.certify.certificate import build_certificate, compute_verdict

_COMPLETE = {"total": 10, "passed": 10, "failed": 0, "skipped": 0, "complete": True}


def test_run_verde_sin_manifiesto_es_inconcluso():
    assert compute_verdict([], confidence="high", manifest=None) == "inconcluso"


def test_run_verde_con_manifiesto_incompleto_es_inconcluso():
    assert compute_verdict([], confidence="high",
                           manifest={"total": 0, "complete": False}) == "inconcluso"


def test_run_verde_con_manifiesto_completo_es_apto():
    assert compute_verdict([], confidence="high", manifest=_COMPLETE) == "apto"


def test_run_con_fallos_reales_sigue_no_apto_aunque_falte_manifiesto():
    verdicts = [{"category": "real", "rule_applied": "R5_real_novel", "requires_approval": False}]
    assert compute_verdict(verdicts, confidence="high", manifest=None) == "no-apto"


def test_run_con_mantenimiento_sigue_reservas_sin_manifiesto():
    verdicts = [{"category": "maintenance", "rule_applied": "R3", "requires_approval": False}]
    assert compute_verdict(verdicts, confidence="high", manifest=None) == "apto-con-reservas"


def test_acta_v3_incluye_execution_manifest():
    cert = build_certificate(
        run={"org_id": "o", "project": "p", "commit_sha": "c", "run_id": "r"},
        verdicts=[], sign_offs=[], mnemo_version="1", model_version="m",
        created_at="2026-01-01", self_eval={"confidence": "high"}, manifest=_COMPLETE)
    assert cert["schema"] == "mnemo.cert.v3"
    assert cert["execution_manifest"] == _COMPLETE
    assert cert["verdict"] == "apto"


def test_acta_v3_run_vacio_sin_manifiesto_es_inconcluso():
    cert = build_certificate(
        run={"org_id": "o", "project": "p", "commit_sha": "c", "run_id": "r"},
        verdicts=[], sign_offs=[], mnemo_version="1", model_version="m",
        created_at="2026-01-01", self_eval={"confidence": "high"}, manifest=None)
    assert cert["verdict"] == "inconcluso"
    assert cert["execution_manifest"] is None


def test_manifiesto_declara_fallos_sin_verdicts_es_inconcluso():
    # cabecera declara fallos pero triaje vacío (parser no extrajo) → inconcluso, no apto
    m = {"total": 3, "passed": 0, "failed": 3, "skipped": 0, "complete": True}
    assert compute_verdict([], confidence="high", manifest=m) == "inconcluso"


def test_flaky_triado_con_manifiesto_completo_sigue_apto():
    # flaky triado (verdicts NO vacío) no se convierte en inconcluso por la guarda de failed
    verdicts = [{"category": "flaky", "requires_approval": False}]
    m = {"total": 3, "passed": 2, "failed": 0, "flaky": 1, "complete": True}
    assert compute_verdict(verdicts, confidence="high", manifest=m) == "apto"
