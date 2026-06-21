import pytest

from src.jira.ingestion_service import JiraIngestionService
from src.jira.models import JiraBug


class _FakeEmbedder:
    def embed(self, text):
        return [0.1] * 384


class _FakeRepo:
    def __init__(self, existing=None):
        self._existing = existing or []
        self.captured = None

    def existing_external_refs(self, *, user_id, org_id):
        return list(self._existing)

    def ingest_run(self, *, user_id, org_id, project, source, items):
        self.captured = {"source": source, "items": items}
        return {"run_id": "r", "ingested": len(items), "known": 0, "novel": len(items)}


class _FakeIntegrations:
    def __init__(self, creds):
        self._creds = creds

    def get_jira_credentials(self, *, user_id, org_id):
        return self._creds


def _bug(key):
    return JiraBug(key=key, summary="Login timeout", description="waited 30s",
                   issue_type="Bug", status="Open", url=f"https://x/browse/{key}")


def test_ingest_bugs_sets_source_and_external_ref():
    repo = _FakeRepo()
    svc = JiraIngestionService(repo=repo, embedder=_FakeEmbedder(),
                               integrations=_FakeIntegrations(None))
    out = svc.ingest_bugs(user_id="u", org_id="o", project="p", bugs=[_bug("B-1")])
    assert repo.captured["source"] == "jira"
    item = repo.captured["items"][0]
    assert item.external_ref == "B-1"
    assert item.external_url == "https://x/browse/B-1"
    assert out["skipped"] == 0


def test_ingest_bugs_dedups_existing():
    repo = _FakeRepo(existing=["B-1"])
    svc = JiraIngestionService(repo=repo, embedder=_FakeEmbedder(),
                               integrations=_FakeIntegrations(None))
    out = svc.ingest_bugs(user_id="u", org_id="o", project="p", bugs=[_bug("B-1"), _bug("B-2")])
    assert out["skipped"] == 1
    assert len(repo.captured["items"]) == 1
    assert repo.captured["items"][0].external_ref == "B-2"


def test_ingest_from_pull_without_config_raises():
    repo = _FakeRepo()
    svc = JiraIngestionService(repo=repo, embedder=_FakeEmbedder(),
                               integrations=_FakeIntegrations(None))
    with pytest.raises(ValueError):
        svc.ingest_from_pull(user_id="u", org_id="o", project="p")
