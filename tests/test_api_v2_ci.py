import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2

SECRET = "testsecret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def make_client(service, monkeypatch, triage=None):
    monkeypatch.setattr(api_v2, "CI_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(api_v2, "CI_SERVICE_USER_ID", "svc-user")
    monkeypatch.setattr(api_v2, "get_ci_ingestion_service", lambda: service)
    if triage is None:
        triage = MagicMock()
        triage.triage_run.return_value = {"flaky": 0, "infra": 0, "maintenance": 0, "real": 0, "unknown": 0}
    monkeypatch.setattr(api_v2, "get_triage_service", lambda: triage)
    app = FastAPI()
    app.include_router(api_v2.router)
    return TestClient(app)


def _body() -> bytes:
    return json.dumps({
        "project": "demo", "org_id": "org-1", "commit_sha": "abc", "source": "playwright",
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html></html>"},
            {"test_name": "home", "status": "pass", "dom": "<html>ok</html>"},
        ],
    }).encode()


def _ok_service():
    service = MagicMock()
    service.ingest_artifact.return_value = {
        "run_id": "r1", "ingested": 1, "known": 0, "novel": 1,
        "results_recorded": 2, "snapshots_saved": 2, "deduplicated": False,
    }
    return service


def test_webhook_valid_signature(monkeypatch):
    service = _ok_service()
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "r1"
    assert data["ingested"] == 1
    assert data["known"] == 0
    assert data["novel"] == 1
    assert data["results_recorded"] == 2
    assert data["snapshots_saved"] == 2
    assert data["deduplicated"] is False
    assert resp.json()["triage"] == {"flaky": 0, "infra": 0, "maintenance": 0, "real": 0, "unknown": 0}
    service.ingest_artifact.assert_called_once()


def test_webhook_invalid_signature(monkeypatch):
    service = _ok_service()
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": "sha256=deadbeef"})
    assert resp.status_code == 401
    service.ingest_artifact.assert_not_called()


def test_webhook_malformed_artifact_is_422(monkeypatch):
    service = _ok_service()
    client = make_client(service, monkeypatch)
    body = b'{"not":"an artifact"}'
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 422


def test_webhook_permission_error_is_403(monkeypatch):
    service = _ok_service()
    service.ingest_artifact.side_effect = PermissionError("not a member")
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 403


def test_webhook_db_error_is_502(monkeypatch):
    service = _ok_service()
    service.ingest_artifact.side_effect = psycopg.OperationalError("db down")
    client = make_client(service, monkeypatch)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 502


def test_webhook_service_account_unconfigured_is_503(monkeypatch):
    monkeypatch.setattr(api_v2, "CI_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(api_v2, "CI_SERVICE_USER_ID", "")
    app = FastAPI()
    app.include_router(api_v2.router)
    client = TestClient(app)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 503


def test_webhook_multitenant_unconfigured_is_503(monkeypatch):
    monkeypatch.setattr(api_v2, "CI_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(api_v2, "CI_SERVICE_USER_ID", "svc-user")
    monkeypatch.setattr(api_v2, "multi_tenant_enabled", lambda: False)
    app = FastAPI()
    app.include_router(api_v2.router)
    client = TestClient(app)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 503


def test_webhook_payload_too_large_is_413(monkeypatch):
    service = _ok_service()
    monkeypatch.setattr(api_v2, "CI_MAX_BODY_BYTES", 10)
    client = make_client(service, monkeypatch)
    body = _body()  # larger than 10 bytes
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 413
    service.ingest_artifact.assert_not_called()


def test_webhook_wrong_org_is_403(monkeypatch):
    service = _ok_service()
    monkeypatch.setattr(api_v2, "CI_SERVICE_ORG_ID", "other-org")
    client = make_client(service, monkeypatch)
    body = _body()  # org_id "org-1"
    resp = client.post("/v2/ci/webhook", content=body,
                       headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 403
    service.ingest_artifact.assert_not_called()


def test_webhook_runs_triage_and_includes_summary(monkeypatch):
    service = _ok_service()  # returns deduplicated=False, run_id="r1"
    triage = MagicMock()
    triage.triage_run.return_value = {"flaky": 1, "infra": 0, "maintenance": 0, "real": 2, "unknown": 0}
    client = make_client(service, monkeypatch, triage=triage)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    triage.triage_run.assert_called_once_with(user_id="svc-user", run_id="r1")
    assert resp.json()["triage"] == {"flaky": 1, "infra": 0, "maintenance": 0, "real": 2, "unknown": 0}


def test_webhook_skips_triage_on_dedup(monkeypatch):
    service = MagicMock()
    service.ingest_artifact.return_value = {
        "run_id": "r1", "ingested": 0, "known": 0, "novel": 0,
        "results_recorded": 0, "snapshots_saved": 0, "deduplicated": True,
    }
    triage = MagicMock()
    client = make_client(service, monkeypatch, triage=triage)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    triage.triage_run.assert_not_called()
    assert resp.json()["triage"] is None


def test_webhook_triage_failure_degrades(monkeypatch):
    service = _ok_service()
    triage = MagicMock()
    triage.triage_run.side_effect = RuntimeError("boom")
    client = make_client(service, monkeypatch, triage=triage)
    body = _body()
    resp = client.post("/v2/ci/webhook", content=body, headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200  # la ingesta no se rompe
    assert resp.json()["triage"] is None


def test_webhook_emits_cert_and_gate_after_triage(monkeypatch):
    service = _ok_service()  # deduplicated=False, run_id="r1"
    client = make_client(service, monkeypatch)
    body = _body()
    cert_svc = MagicMock()
    cert_svc.generate.return_value = {"verdict": "apto", "risk_score": 0}
    gate_svc = MagicMock()
    gate_svc.publish.return_value = {"verdict": "apto", "conclusion": "success", "check_run_url": "u"}
    with patch("src.api_v2.get_certificate_service", return_value=cert_svc), \
         patch("src.api_v2.get_gate_service", return_value=gate_svc):
        resp = client.post("/v2/ci/webhook", content=body,
                           headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "apto"
    assert data["gate"] == "success"
    cert_svc.generate.assert_called_once()
    gate_svc.publish.assert_called_once()


def test_webhook_degrades_when_gate_unavailable(monkeypatch):
    service = _ok_service()  # deduplicated=False, run_id="r1"
    client = make_client(service, monkeypatch)
    body = _body()
    cert_svc = MagicMock()
    cert_svc.generate.return_value = {"verdict": "apto-con-reservas"}
    gate_svc = MagicMock()
    gate_svc.publish.side_effect = RuntimeError("no GitHub App")
    with patch("src.api_v2.get_certificate_service", return_value=cert_svc), \
         patch("src.api_v2.get_gate_service", return_value=gate_svc):
        resp = client.post("/v2/ci/webhook", content=body,
                           headers={"X-Hub-Signature-256": _sign(body)})
    assert resp.status_code == 200  # gate degradó, webhook 200
    data = resp.json()
    assert data["verdict"] == "apto-con-reservas"
    assert data["gate"] is None
