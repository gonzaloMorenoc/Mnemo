"""Tokens de ingesta CI: repositorio (SQL/roles/hash) + endpoints + /ci/ingest."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.ci.ingest_tokens import TOKEN_PREFIX, IngestTokenRepository, _hash
from src.security import AuthenticatedUser


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


def _repo():
    return IngestTokenRepository(db_url="postgres://x")


def _all_sql(cur) -> str:
    return " ".join(str(c.args[0]) for c in cur.execute.call_args_list)


# ---------------------------------------------------------------------------
# Repositorio
# ---------------------------------------------------------------------------

class TestRepo:
    def test_create_returns_plaintext_once_and_stores_hash(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [{"ok": True},
                                    {"id": "t1", "name": "ci", "created_at": None}]
        with patch("src.ci.ingest_tokens.get_pool", return_value=_fake_pool(cur)):
            out = _repo().create_token(user_id="u", org_id="o", name="ci")
        assert out["token"].startswith(TOKEN_PREFIX)
        # lo que va a BD es el sha256, no el claro
        insert_params = cur.execute.call_args_list[1].args[1]
        assert out["token"] not in insert_params
        assert _hash(out["token"]) in insert_params
        assert "('owner','admin')" in _all_sql(cur)   # crear exige rol

    def test_create_requires_owner_admin(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [{"ok": False}]
        with patch("src.ci.ingest_tokens.get_pool", return_value=_fake_pool(cur)):
            assert _repo().create_token(user_id="u", org_id="o", name="ci") is None

    def test_resolve_active_token_updates_last_used(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"id": "t1", "org_id": "o1", "created_by": "u1"}
        with patch("src.ci.ingest_tokens.get_pool", return_value=_fake_pool(cur)):
            info = _repo().resolve(token=TOKEN_PREFIX + "a" * 48)
        assert info == {"token_id": "t1", "org_id": "o1", "created_by": "u1"}
        sql = _all_sql(cur)
        assert "last_used_at=now()" in sql and "revoked_at is null" in sql

    def test_resolve_rejects_bad_prefix_without_db(self):
        with patch("src.ci.ingest_tokens.get_pool") as pool:
            assert _repo().resolve(token="Bearer basura") is None
            assert _repo().resolve(token="") is None
        pool.assert_not_called()

    def test_revoke_cas_requires_owner_admin(self):
        cur = MagicMock()
        cur.rowcount = 1
        with patch("src.ci.ingest_tokens.get_pool", return_value=_fake_pool(cur)):
            assert _repo().revoke_token(user_id="u", token_id="t1") is True
        sql = _all_sql(cur)
        assert "revoked_at=now()" in sql and "revoked_at is null" in sql
        assert "('owner','admin')" in sql


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def make_client(repo, ingestion=None):
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = _user
    app.dependency_overrides[api_v2.get_ingest_token_repo] = lambda: repo
    if ingestion is not None:
        app.dependency_overrides[api_v2.get_ingestion_service] = lambda: ingestion
    return TestClient(app)


def test_create_token_endpoint_returns_token_once():
    repo = MagicMock()
    repo.create_token.return_value = {"id": "t1", "name": "ci", "created_at": None,
                                      "token": "mnemo_it_abc"}
    r = make_client(repo).post("/v2/ingest/tokens", json={"org_id": "o1", "name": "ci"})
    assert r.status_code == 200 and r.json()["token"] == "mnemo_it_abc"


def test_create_token_403_without_role():
    repo = MagicMock()
    repo.create_token.return_value = None
    r = make_client(repo).post("/v2/ingest/tokens", json={"org_id": "o1", "name": "ci"})
    assert r.status_code == 403


def test_revoke_endpoint():
    repo = MagicMock()
    repo.revoke_token.return_value = True
    r = make_client(repo).post("/v2/ingest/tokens/t1/revoke")
    assert r.status_code == 200 and r.json() == {"revoked": True}


# ---------------------------------------------------------------------------
# POST /v2/ci/ingest — ingesta genérica por token
# ---------------------------------------------------------------------------

_JUNIT = b'<?xml version="1.0"?><testsuite tests="1"><testcase name="t"/></testsuite>'


def test_ci_ingest_full_pipeline_with_token():
    repo = MagicMock()
    repo.resolve.return_value = {"token_id": "t1", "org_id": "o1", "created_by": "u9"}
    ingestion = MagicMock()
    ingestion.ingest_report.return_value = {"run_id": "r1", "ingested": 1}
    with patch.object(api_v2, "_post_ingest_pipeline",
                      return_value=({"real": 1}, "no-apto", None)) as pipe:
        r = make_client(repo, ingestion).post(
            "/v2/ci/ingest",
            headers={"Authorization": "Bearer mnemo_it_tok"},
            files={"file": ("junit.xml", _JUNIT, "application/xml")},
            data={"project": "web"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == "r1" and body["verdict"] == "no-apto"
    # el token actúa con la identidad de su creador y su org
    kw = ingestion.ingest_report.call_args.kwargs
    assert kw["user_id"] == "u9" and kw["org_id"] == "o1" and kw["source"] == "auto"
    pipe.assert_called_once_with("u9", "r1")
    repo.resolve.assert_called_once_with(token="mnemo_it_tok")


def test_ci_ingest_accepts_x_mnemo_token_header():
    repo = MagicMock()
    repo.resolve.return_value = {"token_id": "t1", "org_id": "o1", "created_by": "u9"}
    ingestion = MagicMock()
    ingestion.ingest_report.return_value = {"run_id": "r1"}
    with patch.object(api_v2, "_post_ingest_pipeline", return_value=(None, None, None)):
        r = make_client(repo, ingestion).post(
            "/v2/ci/ingest",
            headers={"X-Mnemo-Token": "mnemo_it_tok2"},
            files={"file": ("junit.xml", _JUNIT, "application/xml")},
            data={"project": "web"},
        )
    assert r.status_code == 200
    repo.resolve.assert_called_once_with(token="mnemo_it_tok2")


def test_ci_ingest_invalid_token_401():
    repo = MagicMock()
    repo.resolve.return_value = None
    ingestion = MagicMock()
    r = make_client(repo, ingestion).post(
        "/v2/ci/ingest",
        headers={"Authorization": "Bearer nope"},
        files={"file": ("junit.xml", _JUNIT, "application/xml")},
        data={"project": "web"},
    )
    assert r.status_code == 401
    ingestion.ingest_report.assert_not_called()


def test_ci_ingest_bad_report_400():
    repo = MagicMock()
    repo.resolve.return_value = {"token_id": "t1", "org_id": "o1", "created_by": "u9"}
    ingestion = MagicMock()
    ingestion.ingest_report.side_effect = ValueError("formato no reconocido")
    r = make_client(repo, ingestion).post(
        "/v2/ci/ingest",
        headers={"Authorization": "Bearer mnemo_it_tok"},
        files={"file": ("cosa.bin", b"garbage", "application/octet-stream")},
        data={"project": "web"},
    )
    assert r.status_code == 400
