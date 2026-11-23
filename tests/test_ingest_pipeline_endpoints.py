"""Endpoints de ingesta (auditoría 23-nov-2026): #4, #5, #19b y 03-técnica E9/E10.

- /v2/ingest/report (subida web) encadena triaje + acta + gate y las propuestas.
- /v2/ci/ingest acepta `commit_sha` y `branch` validados.
- Un run deduplicado sin triaje o sin acta relanza el pipeline.
- /ingest/report autentica y comprueba la membresía antes de leer el archivo.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src.security import AuthenticatedUser

_JUNIT = b'<?xml version="1.0"?><testsuite tests="1"><testcase name="t"/></testsuite>'
_RESULT = {"run_id": "r1", "ingested": 1, "known": 0, "novel": 1, "deduplicated": False}


def _user():
    return AuthenticatedUser(user_id="user-1", email="t@e.com", claims={})


def _client(*, ingestion=None, token_repo=None, with_user=True):
    app = FastAPI()
    app.include_router(api_v2.router)
    if with_user:
        app.dependency_overrides[api_v2.get_current_user] = _user
    if ingestion is not None:
        app.dependency_overrides[api_v2.get_ingestion_service] = lambda: ingestion
    if token_repo is not None:
        app.dependency_overrides[api_v2.get_ingest_token_repo] = lambda: token_repo
    return TestClient(app)


def _ingestion(result=None, member=True):
    svc = MagicMock()
    svc.is_member.return_value = member
    svc.ingest_report.return_value = dict(result or _RESULT)
    return svc


def _upload(client, data=None):
    return client.post(
        "/v2/ingest/report",
        data=data or {"project": "web", "source": "junit", "org_id": "org-1"},
        files={"file": ("junit.xml", _JUNIT, "application/xml")},
    )


# ---------------------------------------------------------------------------
# #4 — la subida web tría, emite acta y deja propuestas
# ---------------------------------------------------------------------------

class TestIngestReportPipeline:
    def test_runs_pipeline_and_schedules_proposals(self):
        svc = _ingestion()
        with patch.object(api_v2, "_post_ingest_pipeline",
                          return_value=({"real": 1}, "no-apto", None)) as pipe, \
                patch.object(api_v2, "_propose_knowledge_after_ingest") as propose:
            r = _upload(_client(ingestion=svc))
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == "r1" and body["triage"] == {"real": 1}
        assert body["verdict"] == "no-apto" and body["gate"] is None
        pipe.assert_called_once_with("user-1", "r1")
        propose.assert_called_once_with("user-1", "org-1")

    def test_deduplicated_complete_run_skips_pipeline(self):
        svc = _ingestion({**_RESULT, "deduplicated": True})
        assurance = MagicMock()
        assurance.run_needs_pipeline.return_value = False
        with patch.object(api_v2, "_post_ingest_pipeline") as pipe, \
                patch.object(api_v2, "get_assurance_repo", return_value=assurance), \
                patch.object(api_v2, "_propose_knowledge_after_ingest") as propose:
            r = _upload(_client(ingestion=svc))
        assert r.status_code == 200 and r.json()["deduplicated"] is True
        pipe.assert_not_called()
        propose.assert_not_called()

    def test_non_member_is_rejected_before_reading_the_file(self, monkeypatch):
        # La subida exige membresía Y rol (matriz de roles): sin rol en la org → 403.
        import src.orgs.access as access_module

        class _NoRole:
            def role_of(self, *, org_id, user_id):
                return None

            def org_of(self, *, resource, resource_id):
                return None

        monkeypatch.setattr(access_module, "_access_factory",
                            lambda: access_module.OrgAccess(_NoRole()))
        svc = _ingestion(member=False)
        with patch.object(api_v2, "_read_upload_capped_async") as read:
            r = _upload(_client(ingestion=svc))
        assert r.status_code == 403
        read.assert_not_called()
        svc.ingest_report.assert_not_called()

    def test_requires_auth(self):
        r = _upload(_client(ingestion=_ingestion(), with_user=False))
        assert r.status_code == 401

    def test_missing_fields_422(self):
        r = _client(ingestion=_ingestion()).post(
            "/v2/ingest/report", data={"project": "web"},
            files={"file": ("junit.xml", _JUNIT, "application/xml")})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# #19b — un run deduplicado sin triaje/acta relanza el pipeline
# ---------------------------------------------------------------------------

def _token_repo(acting="u9"):
    repo = MagicMock()
    repo.resolve.return_value = {"token_id": "t1", "org_id": "o1", "created_by": "u9",
                                 "acting_user_id": acting}
    return repo


def _ci_post(client, data=None):
    return client.post(
        "/v2/ci/ingest",
        headers={"Authorization": "Bearer mnemo_it_tok"},
        files={"file": ("junit.xml", _JUNIT, "application/xml")},
        data=data or {"project": "web"},
    )


def test_ci_ingest_deduplicated_run_without_triage_reruns_pipeline():
    svc = _ingestion({**_RESULT, "deduplicated": True})
    assurance = MagicMock()
    assurance.run_needs_pipeline.return_value = True
    with patch.object(api_v2, "_post_ingest_pipeline",
                      return_value=({"real": 1}, "apto", None)) as pipe, \
            patch.object(api_v2, "get_assurance_repo", return_value=assurance):
        r = _ci_post(_client(ingestion=svc, token_repo=_token_repo()))
    assert r.status_code == 200 and r.json()["verdict"] == "apto"
    pipe.assert_called_once_with("u9", "r1")
    assurance.run_needs_pipeline.assert_called_once_with(user_id="u9", run_id="r1")


def test_webhook_deduplicated_run_without_cert_reruns_pipeline(monkeypatch):
    ci = MagicMock()
    ci.ingest_artifact.return_value = {**_RESULT, "results_recorded": 0,
                                       "snapshots_saved": 0, "deduplicated": True}
    assurance = MagicMock()
    assurance.run_needs_pipeline.return_value = True
    monkeypatch.setattr(api_v2, "CI_SERVICE_USER_ID", "svc")
    with patch.object(api_v2, "get_ci_ingestion_service", return_value=ci), \
            patch.object(api_v2, "get_assurance_repo", return_value=assurance), \
            patch.object(api_v2, "_post_ingest_pipeline",
                         return_value=({"real": 0}, "apto", None)) as pipe:
        resp = api_v2._process_ci_artifact(MagicMock(org_id="o1"))
    assert resp.verdict == "apto"
    pipe.assert_called_once_with("svc", "r1")


# ---------------------------------------------------------------------------
# #5 — /ci/ingest acepta commit_sha y branch (validados)
# ---------------------------------------------------------------------------

class TestCiIngestCommit:
    def test_commit_and_branch_reach_the_service(self):
        svc = _ingestion()
        with patch.object(api_v2, "_post_ingest_pipeline", return_value=(None, None, None)):
            r = _ci_post(_client(ingestion=svc, token_repo=_token_repo()),
                         data={"project": "web", "commit_sha": "ABCdef1234567",
                               "branch": "feature/pago-1"})
        assert r.status_code == 200
        kw = svc.ingest_report.call_args.kwargs
        assert kw["commit_sha"] == "abcdef1234567"   # normalizado a minúsculas
        assert kw["branch"] == "feature/pago-1"

    def test_without_commit_fields_they_are_none(self):
        svc = _ingestion()
        with patch.object(api_v2, "_post_ingest_pipeline", return_value=(None, None, None)):
            r = _ci_post(_client(ingestion=svc, token_repo=_token_repo()))
        assert r.status_code == 200
        kw = svc.ingest_report.call_args.kwargs
        assert kw["commit_sha"] is None and kw["branch"] is None

    @pytest.mark.parametrize("sha", ["abc12", "z" * 40, "a" * 41, "abc1234; rm -rf"])
    def test_invalid_commit_sha_400(self, sha):
        svc = _ingestion()
        r = _ci_post(_client(ingestion=svc, token_repo=_token_repo()),
                     data={"project": "web", "commit_sha": sha})
        assert r.status_code == 400
        svc.ingest_report.assert_not_called()

    @pytest.mark.parametrize("branch", ["x" * 256, "rama\ncon-salto", "rama\x00nul"])
    def test_invalid_branch_400(self, branch):
        svc = _ingestion()
        r = _ci_post(_client(ingestion=svc, token_repo=_token_repo()),
                     data={"project": "web", "branch": branch})
        assert r.status_code == 400
        svc.ingest_report.assert_not_called()


def test_ci_ingest_resolves_token_off_the_event_loop():
    """03-técnica E10: `resolve` (un UPDATE en Postgres) no corre en el event loop."""
    svc = _ingestion()
    calls = []
    real = api_v2.run_in_threadpool

    async def spy(fn, *args, **kwargs):
        calls.append(getattr(fn, "__name__", repr(fn)))
        return await real(fn, *args, **kwargs)

    repo = _token_repo()
    repo.resolve.__name__ = "resolve"
    with patch.object(api_v2, "run_in_threadpool", side_effect=spy), \
            patch.object(api_v2, "_post_ingest_pipeline", return_value=(None, None, None)):
        r = _ci_post(_client(ingestion=svc, token_repo=repo))
    assert r.status_code == 200
    assert calls and calls[0] == "resolve"


def test_webhook_chunked_body_over_cap_413_without_reading_it_all(monkeypatch):
    """Sin Content-Length (chunked) el tope se aplica mientras se lee el cuerpo."""
    monkeypatch.setattr(api_v2, "CI_MAX_BODY_BYTES", 100)
    # Sin CI_SERVICE_ORG_ID el webhook global responde 503 sin leer nada.
    monkeypatch.setattr(api_v2, "CI_SERVICE_ORG_ID", "o1")

    def chunks():
        for _ in range(50):
            yield b"x" * 10

    r = _client().post("/v2/ci/webhook", content=chunks())
    assert r.status_code == 413
