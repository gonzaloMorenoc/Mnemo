from unittest.mock import MagicMock

from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact


def _artifact(run_uid=None):
    return CiRunArtifact.model_validate({
        "project": "demo", "org_id": "org-1", "commit_sha": "abc", "run_uid": run_uid,
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html>fail</html>"},
            {"test_name": "home", "status": "pass", "dom": "<html>ok</html>"},
            {"test_name": "skip_me", "status": "skipped"},
        ],
    })


def _service():
    repo = MagicMock()
    repo.ingest_ci_run.return_value = {
        "run_id": "r1", "ingested": 1, "known": 0, "novel": 1,
        "results_recorded": 3, "snapshots_saved": 2, "deduplicated": False,
    }
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 384
    return CiIngestionService(repo=repo, embedder=embedder), repo


def test_calls_ingest_ci_run_once_with_items_results_snapshots():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact(run_uid="u-1"))
    repo.ingest_ci_run.assert_called_once()
    _, kw = repo.ingest_ci_run.call_args
    assert kw["org_id"] == "org-1" and kw["commit_sha"] == "abc" and kw["run_uid"] == "u-1"
    # items = solo fallos (login); results = todos los tests; snapshots = los que tienen dom
    assert len(kw["items"]) == 1 and kw["items"][0].rec.test_name == "login"
    assert {r["test_name"] for r in kw["results"]} == {"login", "home", "skip_me"}
    assert {s["test_name"]: s["kind"] for s in kw["snapshots"]} == {"login": "failure", "home": "last_green"}


def test_returns_repo_result_passthrough():
    svc, _ = _service()
    out = svc.ingest_artifact(user_id="svc", artifact=_artifact())
    assert out["run_id"] == "r1" and out["deduplicated"] is False
    assert out["results_recorded"] == 3 and out["snapshots_saved"] == 2
