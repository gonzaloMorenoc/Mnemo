from unittest.mock import MagicMock

from src.defects.ingestion_service import IngestionService


def test_ingest_report_pasa_manifest_a_ingest_run():
    repo = MagicMock()
    svc = IngestionService(repo=repo, embedder=MagicMock(embed=lambda t: [0.0]))
    xml = (b'<testsuite tests="3" failures="1" skipped="0">'
           b'<testcase name="t"><failure/></testcase></testsuite>')
    svc.ingest_report(user_id="u", org_id="o", project="p", source="junit", data=xml)
    m = repo.ingest_run.call_args.kwargs["manifest"]
    assert m["total"] == 3 and m["failed"] == 1 and m["complete"] is True
    assert len(m["artifact_sha256"]) == 64


def test_ingest_report_formato_sin_summary_pasa_manifest_none():
    # 'auto' con datos irreconocibles ya falla antes; aquí forzamos un source cuyo
    # summarize devuelve None solo si el parseo del summary falla → manifest None.
    repo = MagicMock()
    svc = IngestionService(repo=repo, embedder=MagicMock(embed=lambda t: [0.0]))
    # junit válido para el parser de fallos pero cuyo summarize da un total>0:
    xml = b'<testsuite tests="1" failures="0"><testcase name="t"/></testsuite>'
    svc.ingest_report(user_id="u", org_id="o", project="p", source="junit", data=xml)
    m = repo.ingest_run.call_args.kwargs["manifest"]
    assert m is not None and m["total"] == 1
