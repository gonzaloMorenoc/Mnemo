"""B3 — /ingest/report idempotente: el servicio deriva un run_uid del contenido.

Subir dos veces el MISMO archivo debe producir el MISMO run_uid (la capa de
repositorio deduplica por (org_id, run_uid)); archivos o proyectos distintos
deben producir run_uid distintos.
"""
from unittest.mock import MagicMock

from src.defects.ingestion_service import IngestionService

_JUNIT = (
    b'<testsuite tests="1" failures="1">'
    b'<testcase classname="C" name="t1">'
    b'<failure message="AssertionError: boom">trace</failure>'
    b"</testcase></testsuite>"
)

_JUNIT_OTHER = (
    b'<testsuite tests="1" failures="1">'
    b'<testcase classname="C" name="t2">'
    b'<failure message="TimeoutError: slow">trace</failure>'
    b"</testcase></testsuite>"
)


def _service():
    repo = MagicMock()
    repo.ingest_run.return_value = {
        "run_id": "r1", "ingested": 1, "known": 0, "novel": 1, "deduplicated": False,
    }
    embedder = MagicMock()
    embedder.embed.return_value = [0.1] * 384
    return IngestionService(repo=repo, embedder=embedder), repo


def _run_uid(repo) -> str:
    _, kw = repo.ingest_run.call_args
    return kw["run_uid"]


def test_same_file_and_project_produce_same_run_uid():
    svc, repo = _service()
    svc.ingest_report(user_id="u1", org_id="o1", project="web", source="junit", data=_JUNIT)
    first = _run_uid(repo)
    svc.ingest_report(user_id="u1", org_id="o1", project="web", source="junit", data=_JUNIT)
    second = _run_uid(repo)
    assert isinstance(first, str) and first
    assert first == second


def test_different_content_produces_different_run_uid():
    svc, repo = _service()
    svc.ingest_report(user_id="u1", org_id="o1", project="web", source="junit", data=_JUNIT)
    first = _run_uid(repo)
    svc.ingest_report(user_id="u1", org_id="o1", project="web", source="junit",
                      data=_JUNIT_OTHER)
    second = _run_uid(repo)
    assert first != second


def test_different_project_produces_different_run_uid():
    svc, repo = _service()
    svc.ingest_report(user_id="u1", org_id="o1", project="web", source="junit", data=_JUNIT)
    first = _run_uid(repo)
    svc.ingest_report(user_id="u1", org_id="o1", project="mobile", source="junit", data=_JUNIT)
    second = _run_uid(repo)
    assert first != second
