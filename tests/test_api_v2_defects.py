from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(*, repo=None, service=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if service is not None:
        app.dependency_overrides[api_v2.get_ingestion_service] = lambda: service
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_ingest_report_happy():
    service = MagicMock()
    service.ingest_report.return_value = {"run_id": "r1", "ingested": 2, "known": 1, "novel": 1}
    client = make_client(service=service)
    resp = client.post(
        "/v2/ingest/report",
        data={"project": "proj-a", "source": "allure", "org_id": "org-1"},
        files={"file": ("r.json", b"[]", "application/json")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"run_id": "r1", "ingested": 2, "known": 1, "novel": 1,
                           "deduplicated": False}
    kw = service.ingest_report.call_args.kwargs
    assert kw["org_id"] == "org-1" and kw["source"] == "allure" and kw["data"] == b"[]"


def test_ingest_report_rejects_oversized_file(monkeypatch):
    # B9: subida por encima de INGEST_MAX_BYTES → 413, sin cargar todo en memoria.
    monkeypatch.setattr(api_v2, "INGEST_MAX_BYTES", 10)
    service = MagicMock()
    client = make_client(service=service)
    resp = client.post(
        "/v2/ingest/report",
        data={"project": "p", "source": "auto", "org_id": "o"},
        files={"file": ("big.xml", b"x" * 5000, "application/xml")},
    )
    assert resp.status_code == 413
    service.ingest_report.assert_not_called()


def test_ingest_report_unknown_source_is_400():
    service = MagicMock()
    service.ingest_report.side_effect = ValueError("unsupported source: xml")
    client = make_client(service=service)
    resp = client.post("/v2/ingest/report",
                       data={"project": "p", "source": "xml", "org_id": "o"},
                       files={"file": ("r", b"[]", "application/json")})
    assert resp.status_code == 400


def test_ingest_report_non_member_is_403():
    service = MagicMock()
    service.ingest_report.side_effect = PermissionError("not a member")
    client = make_client(service=service)
    resp = client.post("/v2/ingest/report",
                       data={"project": "p", "source": "allure", "org_id": "o"},
                       files={"file": ("r", b"[]", "application/json")})
    assert resp.status_code == 403


def test_ingest_report_requires_auth():
    client = make_client(service=MagicMock(), with_user=False)
    resp = client.post("/v2/ingest/report",
                       data={"project": "p", "source": "allure", "org_id": "o"},
                       files={"file": ("r", b"[]", "application/json")})
    assert resp.status_code == 401


def test_list_defects_maps_response():
    repo = MagicMock()
    repo.list_defects.return_value = [{
        "id": "f1", "title": "Timeout", "status": "open", "occurrence_count": 2,
        "first_seen": "2026-06-19T10:00:00", "last_seen": "2026-06-20T10:00:00",
        "projects": ["proj-a", "proj-b"],
    }]
    client = make_client(repo=repo)
    resp = client.get("/v2/defects", params={"org_id": "org-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == "f1" and body[0]["projects"] == ["proj-a", "proj-b"]
    assert repo.list_defects.call_args.kwargs["org_id"] == "org-1"


def test_defect_lineage_maps_response():
    repo = MagicMock()
    repo.get_lineage.return_value = {
        "family": {"id": "f1", "title": "Timeout", "status": "open", "occurrence_count": 2},
        "failures": [{"id": "x", "test_name": "t", "error_type": "TimeoutException",
                      "project": "proj-a", "source": "allure", "created_at": "2026-06-19T10:00:00"}],
    }
    client = make_client(repo=repo)
    resp = client.get("/v2/defects/f1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["family"]["id"] == "f1"
    assert body["failures"][0]["project"] == "proj-a"


def test_defect_lineage_not_found_returns_empty_family():
    repo = MagicMock()
    repo.get_lineage.return_value = {"family": None, "failures": []}
    client = make_client(repo=repo)
    resp = client.get("/v2/defects/missing")
    assert resp.status_code == 200
    assert resp.json()["family"] is None
