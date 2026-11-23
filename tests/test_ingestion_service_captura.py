"""IngestionService (subida de reports): commit, rama, resultados por test y
membresía ANTES de embeber (auditoría 23-nov: #5 y 03-técnica E9)."""
from unittest.mock import MagicMock

import pytest

from src.defects.ingestion_service import IngestionService

_JUNIT = (
    b'<testsuite tests="2" failures="1">'
    b'<testcase classname="C" name="ok"/>'
    b'<testcase classname="C" name="ko"><failure message="AssertionError: boom">t</failure>'
    b"</testcase></testsuite>"
)


def _service(member: bool = True):
    repo = MagicMock()
    repo.is_member.return_value = member
    repo.ingest_run.return_value = {"run_id": "r1", "ingested": 1, "known": 0, "novel": 1,
                                    "deduplicated": False}
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 384
    return IngestionService(repo=repo, embedder=embedder), repo, embedder


def test_commit_sha_and_branch_reach_run_and_manifest():
    svc, repo, _ = _service()
    svc.ingest_report(user_id="u", org_id="o", project="web", source="junit", data=_JUNIT,
                      commit_sha="abc1234", branch="feature/x")
    kw = repo.ingest_run.call_args.kwargs
    assert kw["commit_sha"] == "abc1234"
    assert kw["manifest"]["commit_sha"] == "abc1234"
    assert kw["manifest"]["branch"] == "feature/x"


def test_without_commit_manifest_keeps_its_shape():
    svc, repo, _ = _service()
    svc.ingest_report(user_id="u", org_id="o", project="web", source="junit", data=_JUNIT)
    kw = repo.ingest_run.call_args.kwargs
    assert kw["commit_sha"] is None
    assert kw["manifest"]["commit_sha"] is None
    assert "branch" not in kw["manifest"]  # actas previas: mismo contenido firmado


def test_per_test_results_including_passed_are_persisted():
    svc, repo, _ = _service()
    svc.ingest_report(user_id="u", org_id="o", project="web", source="junit", data=_JUNIT)
    results = repo.ingest_run.call_args.kwargs["results"]
    assert {(r["test_name"], r["status"]) for r in results} == {("C.ok", "pass"),
                                                                 ("C.ko", "fail")}


def test_non_member_is_rejected_before_embedding():
    svc, repo, embedder = _service(member=False)
    with pytest.raises(PermissionError):
        svc.ingest_report(user_id="u", org_id="ajena", project="web", source="junit",
                          data=_JUNIT)
    embedder.embed.assert_not_called()
    repo.ingest_run.assert_not_called()
