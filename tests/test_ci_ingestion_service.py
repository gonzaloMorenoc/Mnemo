from unittest.mock import MagicMock

from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact


def _artifact():
    return CiRunArtifact.model_validate({
        "project": "demo", "org_id": "org-1", "commit_sha": "abc",
        "tests": [
            {"test_name": "login", "status": "fail",
             "message": "TimeoutError: locator not found", "dom": "<html>fail</html>"},
            {"test_name": "home", "status": "pass", "dom": "<html>ok</html>"},
            {"test_name": "skip_me", "status": "skipped"},
        ],
    })


def _service():
    repo = MagicMock()
    repo.ingest_run.return_value = {"run_id": "r1", "ingested": 1, "known": 0, "novel": 1}
    repo.record_test_results.return_value = 3
    repo.save_dom_snapshots.return_value = 2
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 384
    return CiIngestionService(repo=repo, embedder=embedder), repo


def test_ingest_run_called_with_commit_sha_and_only_failures():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact())
    _, kwargs = repo.ingest_run.call_args
    assert kwargs["commit_sha"] == "abc"
    assert kwargs["org_id"] == "org-1"
    # Solo el fallo (login) se convierte en item del DNA
    assert len(kwargs["items"]) == 1
    assert kwargs["items"][0].rec.test_name == "login"


def test_records_all_test_results_including_pass_and_skip():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact())
    _, kwargs = repo.record_test_results.call_args
    assert kwargs["run_id"] == "r1"
    assert {r["test_name"] for r in kwargs["results"]} == {"login", "home", "skip_me"}


def test_saves_dom_snapshots_only_for_tests_with_dom():
    svc, repo = _service()
    svc.ingest_artifact(user_id="svc", artifact=_artifact())
    _, kwargs = repo.save_dom_snapshots.call_args
    snaps = {s["test_name"]: s["kind"] for s in kwargs["snapshots"]}
    assert snaps == {"login": "failure", "home": "last_green"}


def test_returns_aggregate_counts():
    svc, _ = _service()
    out = svc.ingest_artifact(user_id="svc", artifact=_artifact())
    assert out["run_id"] == "r1" and out["novel"] == 1
    assert out["results_recorded"] == 3 and out["snapshots_saved"] == 2
