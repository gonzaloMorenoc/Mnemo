import pytest

from src.defects.ingestion_service import IngestionService

TESTNG_XML = b"""<?xml version="1.0"?>
<testng-results>
  <suite name="S"><test name="T"><class name="C">
    <test-method status="FAIL" name="m">
      <exception class="E"><message><![CDATA[boom 30000ms]]></message></exception>
    </test-method>
  </class></test></suite>
</testng-results>"""


class _FakeEmbedder:
    def embed(self, text):
        return [0.1] * 384


class _CapturingRepo:
    def __init__(self):
        self.captured = None

    def ingest_run(self, *, user_id, org_id, project, source, items, run_uid=None):
        self.captured = {"source": source, "items": items, "run_uid": run_uid}
        return {"run_id": "r", "ingested": len(items), "known": 0, "novel": len(items),
                "deduplicated": False}


def _service():
    repo = _CapturingRepo()
    return IngestionService(repo=repo, embedder=_FakeEmbedder()), repo


def test_ingest_report_auto_detects_testng():
    service, repo = _service()
    service.ingest_report(user_id="u", org_id="o", project="p", source="auto", data=TESTNG_XML)
    assert repo.captured["source"] == "testng"
    assert len(repo.captured["items"]) == 1


def test_ingest_report_auto_unknown_raises():
    service, _ = _service()
    with pytest.raises(ValueError):
        service.ingest_report(user_id="u", org_id="o", project="p", source="auto",
                              data=b"not a report")


def test_ingest_report_explicit_source_used():
    service, repo = _service()
    service.ingest_report(user_id="u", org_id="o", project="p", source="testng", data=TESTNG_XML)
    assert repo.captured["source"] == "testng"
