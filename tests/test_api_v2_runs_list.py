"""Histórico de runs: GET /v2/runs + forma del SQL de list_runs."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.defects.repository import AssuranceRepository
from src.security import AuthenticatedUser


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(repo):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    return TestClient(app)


RUN = {"id": "r1", "project": "web", "source": "junit", "commit_sha": "abc123",
       "created_at": "2026-07-22T00:00:00+00:00", "verdict": "apto",
       "risk_score": 10, "failures": 2}


def test_list_runs_passes_filters():
    repo = MagicMock()
    repo.list_runs.return_value = [RUN]
    r = make_client(repo).get("/v2/runs", params={"org_id": "o1", "project": "web",
                                                  "limit": 10, "offset": 5})
    assert r.status_code == 200 and r.json()[0]["id"] == "r1"
    repo.list_runs.assert_called_once_with(
        user_id="user-1", org_id="o1", project="web", limit=10, offset=5)


def test_list_runs_defaults():
    repo = MagicMock()
    repo.list_runs.return_value = []
    r = make_client(repo).get("/v2/runs", params={"org_id": "o1"})
    assert r.status_code == 200 and r.json() == []
    kw = repo.list_runs.call_args.kwargs
    assert kw["project"] is None and kw["limit"] == 50 and kw["offset"] == 0


# ── forma del SQL (mock del pool) ────────────────────────────────────────────

def _fake_pool(cur):
    conn = MagicMock()
    cur_ctx = MagicMock()
    cur_ctx.__enter__ = MagicMock(return_value=cur)
    cur_ctx.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur_ctx
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = ctx
    return pool


def _sql(cur) -> str:
    return " ".join(str(c.args[0]) for c in cur.execute.call_args_list)


def test_list_runs_sql_shape_and_membership():
    repo = AssuranceRepository(db_url="postgres://x")
    cur = MagicMock()
    cur.fetchone.return_value = {"ok": True}
    cur.fetchall.return_value = []
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
        repo.list_runs(user_id="u", org_id="o", project="web", limit=10, offset=5)
    sql = _sql(cur)
    assert "from public.memberships" in sql          # membership-gated
    assert "left join lateral" in sql                # veredicto del acta más reciente
    assert "and r.project = %s" in sql               # filtro por proyecto
    assert "order by r.created_at desc" in sql       # por fecha


def test_list_runs_non_member_returns_empty():
    repo = AssuranceRepository(db_url="postgres://x")
    cur = MagicMock()
    cur.fetchone.return_value = {"ok": False}
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
        out = repo.list_runs(user_id="u", org_id="o")
    assert out == []
    # _set_claims (2) + membership (1); NO llegó a la query de runs
    assert cur.execute.call_count == 3
    assert "left join lateral" not in _sql(cur)


def test_list_runs_caps_limit_to_100():
    repo = AssuranceRepository(db_url="postgres://x")
    cur = MagicMock()
    cur.fetchone.return_value = {"ok": True}
    cur.fetchall.return_value = []
    with patch("src.defects.repository.get_pool", return_value=_fake_pool(cur)):
        repo.list_runs(user_id="u", org_id="o", limit=5000)
    params = cur.execute.call_args_list[-1].args[1]
    assert 100 in params and 5000 not in params
