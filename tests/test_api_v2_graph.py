"""Tests for /v2/graph and /v2/graph/gaps endpoints (Task 3 — QA Memory Fase 2)."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


_GRAPH_RESPONSE = {
    "nodes": [
        {"id": "n1", "type": "knowledge", "label": "Lección checkout", "kind": "leccion", "domain": "checkout"},
    ],
    "edges": [
        {"source": "n1", "target": "domain:checkout", "relation": "pertenece"},
    ],
}

_GAPS_RESPONSE = [
    {
        "kind": "defecto_sin_conocimiento",
        "title": "Timeout en pago",
        "severity": "alta",
        "affected": "fam-1",
        "recommendation": "Crea una lección para documentar este defecto.",
    }
]


def make_client(*, with_user: bool = True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /v2/graph
# ---------------------------------------------------------------------------

def test_get_graph_returns_nodes_and_edges():
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = _GRAPH_RESPONSE

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        r = make_client().get("/v2/graph?org_id=org-1")

    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body and "edges" in body
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["id"] == "n1"


def test_get_graph_no_auth_returns_401():
    r = make_client(with_user=False).get("/v2/graph?org_id=org-1")
    assert r.status_code == 401


def test_get_graph_limit_capped_at_500():
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = {"nodes": [], "edges": []}

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        r = make_client().get("/v2/graph?org_id=org-1&limit=9999")

    assert r.status_code == 200
    _call_kwargs = mock_svc.build_graph.call_args.kwargs
    assert _call_kwargs["limit"] <= 500


def test_get_graph_limit_not_exceeded_below_500():
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = {"nodes": [], "edges": []}

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        r = make_client().get("/v2/graph?org_id=org-1&limit=100")

    assert r.status_code == 200
    _call_kwargs = mock_svc.build_graph.call_args.kwargs
    assert _call_kwargs["limit"] == 100


def test_get_graph_focus_passed_through():
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = {"nodes": [], "edges": []}

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        r = make_client().get("/v2/graph?org_id=org-1&focus=n1")

    assert r.status_code == 200
    _call_kwargs = mock_svc.build_graph.call_args.kwargs
    assert _call_kwargs["focus"] == "n1"


def test_get_graph_focus_none_by_default():
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = {"nodes": [], "edges": []}

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        r = make_client().get("/v2/graph?org_id=org-1")

    assert r.status_code == 200
    _call_kwargs = mock_svc.build_graph.call_args.kwargs
    assert _call_kwargs["focus"] is None


def test_get_graph_non_member_returns_empty():
    """Service returns empty graph for non-member — endpoint relays that without error."""
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = {"nodes": [], "edges": []}

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        r = make_client().get("/v2/graph?org_id=org-foreign")

    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] == [] and body["edges"] == []


def test_get_graph_passes_user_id_and_org_id():
    mock_svc = MagicMock()
    mock_svc.build_graph.return_value = {"nodes": [], "edges": []}

    with patch.object(api_v2, "GraphService", return_value=mock_svc):
        make_client().get("/v2/graph?org_id=org-42")

    mock_svc.build_graph.assert_called_once_with(
        user_id="user-1",
        org_id="org-42",
        focus=None,
        limit=200,
    )


# ---------------------------------------------------------------------------
# GET /v2/graph/gaps
# ---------------------------------------------------------------------------

def test_get_graph_gaps_returns_list():
    with patch.object(api_v2, "detect_gaps", return_value=_GAPS_RESPONSE):
        r = make_client().get("/v2/graph/gaps?org_id=org-1")

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["kind"] == "defecto_sin_conocimiento"


def test_get_graph_gaps_no_auth_returns_401():
    r = make_client(with_user=False).get("/v2/graph/gaps?org_id=org-1")
    assert r.status_code == 401


def test_get_graph_gaps_non_member_returns_empty():
    """Service returns [] for non-member — endpoint relays empty list."""
    with patch.object(api_v2, "detect_gaps", return_value=[]):
        r = make_client().get("/v2/graph/gaps?org_id=org-foreign")

    assert r.status_code == 200
    assert r.json() == []


def test_get_graph_gaps_passes_user_id_and_org_id():
    mock_detect = MagicMock(return_value=[])

    with patch.object(api_v2, "detect_gaps", mock_detect):
        make_client().get("/v2/graph/gaps?org_id=org-77")

    mock_detect.assert_called_once_with(user_id="user-1", org_id="org-77")
