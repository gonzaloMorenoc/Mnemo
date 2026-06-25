from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, repo=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if repo is not None:
        app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


def test_set_label_ok():
    repo = MagicMock()
    repo.set_family_label.return_value = True
    resp = _client(repo=repo).patch("/v2/defects/fam-1/label", json={"label": "flaky"})
    assert resp.status_code == 200 and resp.json()["label"] == "flaky"
    assert repo.set_family_label.call_args.kwargs["family_id"] == "fam-1"


def test_set_label_invalid_is_422():
    repo = MagicMock()
    repo.set_family_label.side_effect = ValueError("invalid label: 'bogus'")
    resp = _client(repo=repo).patch("/v2/defects/fam-1/label", json={"label": "bogus"})
    assert resp.status_code == 422


def test_set_label_not_found_is_404():
    repo = MagicMock()
    repo.set_family_label.return_value = False
    resp = _client(repo=repo).patch("/v2/defects/fam-1/label", json={"label": "flaky"})
    assert resp.status_code == 404


def test_metrics_ok():
    repo = MagicMock()
    repo.get_calibration_metrics.return_value = {
        "total": 3, "aciertos": 2, "accuracy": 0.6667,
        "familias_calibradas": 2, "por_categoria": {"flaky": 2, "real": 1}}
    resp = _client(repo=repo).get("/v2/calibration/metrics?org_id=org-1")
    assert resp.status_code == 200 and resp.json()["total"] == 3


def test_metrics_non_member_is_404():
    repo = MagicMock()
    repo.get_calibration_metrics.return_value = None
    assert _client(repo=repo).get("/v2/calibration/metrics?org_id=org-1").status_code == 404


def test_endpoints_require_auth():
    assert _client(repo=MagicMock(), with_user=False).get(
        "/v2/calibration/metrics?org_id=o").status_code == 401
