import json

import pytest

from src.defects.ingestion_service import IngestionService


class FakeEmbedder:
    def embed(self, text: str):
        return [0.1, 0.2]


class FakeRepo:
    def __init__(self):
        self.calls = []

    def ingest_run(self, **kwargs):
        self.calls.append(kwargs)
        items = kwargs["items"]
        return {"run_id": "r1", "ingested": len(items), "known": 0, "novel": len(items)}


def test_ingest_report_parses_sanitizes_embeds_and_delegates():
    repo = FakeRepo()
    svc = IngestionService(repo=repo, embedder=FakeEmbedder())
    data = json.dumps([{
        "name": "test_login", "status": "failed",
        "statusDetails": {"message": "TimeoutException at host 10.0.0.1", "trace": "at A.java:1"},
    }]).encode()
    out = svc.ingest_report(user_id="u", org_id="o", project="proj-a", source="allure", data=data)
    assert out["ingested"] == 1
    item = repo.calls[0]["items"][0]
    assert "10.0.0.1" not in item.rec.message
    assert item.fingerprint and item.embedding == [0.1, 0.2]
    assert repo.calls[0]["org_id"] == "o" and repo.calls[0]["project"] == "proj-a"


def test_ingest_report_rejects_unknown_source():
    svc = IngestionService(repo=FakeRepo(), embedder=FakeEmbedder())
    with pytest.raises(ValueError):
        svc.ingest_report(user_id="u", org_id="o", project="p", source="xml", data=b"[]")


def test_ingest_report_empty_report_yields_zero():
    repo = FakeRepo()
    svc = IngestionService(repo=repo, embedder=FakeEmbedder())
    out = svc.ingest_report(user_id="u", org_id="o", project="p", source="allure", data=b"[]")
    assert out["ingested"] == 0
