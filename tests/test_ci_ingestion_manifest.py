from unittest.mock import MagicMock

from src.ci.ingestion_service import CiIngestionService
from src.ci.models import CiRunArtifact, CiTestResult


def test_webhook_computa_manifest_de_los_tests():
    repo = MagicMock()
    svc = CiIngestionService(repo=repo, embedder=MagicMock(embed=lambda t: [0.0]))
    art = CiRunArtifact(project="p", org_id="o", commit_sha="c1", source="playwright", tests=[
        CiTestResult(test_name="a", status="pass"),
        CiTestResult(test_name="b", status="fail"),
        CiTestResult(test_name="c", status="flaky"),
        CiTestResult(test_name="d", status="skipped"),
    ])
    svc.ingest_artifact(user_id="u", artifact=art)
    m = repo.ingest_ci_run.call_args.kwargs["manifest"]
    assert (m["total"], m["passed"], m["failed"], m["flaky"], m["skipped"]) == (4, 1, 1, 1, 1)
    assert m["complete"] is True and m["commit_sha"] == "c1"
    assert len(m["artifact_sha256"]) == 64
