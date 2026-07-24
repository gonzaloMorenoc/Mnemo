import pytest
from unittest.mock import MagicMock

from src.certify.service import CertificateService


def _svc(is_admin):
    cert_repo = MagicMock()
    cert_repo.get_run_meta.return_value = {"org_id": "o", "project": "p", "commit_sha": "c",
                                           "manifest": None}
    cert_repo.is_org_admin.return_value = is_admin
    repo = MagicMock()
    repo.get_triage_for_run.return_value = []
    repo.count_failures_for_run.return_value = 0
    repo.get_calibration_metrics.return_value = {}
    return CertificateService(repo=repo, cert_repo=cert_repo, private_key="k", public_key="pk",
                              mnemo_version="1", model_version="m")


def test_miembro_raso_no_puede_emitir_a_mano():
    svc = _svc(is_admin=False)
    with pytest.raises(PermissionError):
        svc.generate(user_id="u", run_id="r", created_at="2026-01-01", require_admin=True)


def test_owner_admin_si_puede_emitir_a_mano(monkeypatch):
    svc = _svc(is_admin=True)
    monkeypatch.setattr("src.certify.service.sign", lambda c, k: "sig")
    out = svc.generate(user_id="u", run_id="r", created_at="2026-01-01", require_admin=True)
    assert out["verdict"] == "sin_confirmar"  # run vacío sin manifiesto


def test_webhook_auto_emite_sin_require_admin(monkeypatch):
    svc = _svc(is_admin=False)  # service user NO es admin
    monkeypatch.setattr("src.certify.service.sign", lambda c, k: "sig")
    # require_admin=False (default) → NO exige admin → no lanza
    out = svc.generate(user_id="svc", run_id="r", created_at="2026-01-01")
    assert out["verdict"] == "sin_confirmar"
