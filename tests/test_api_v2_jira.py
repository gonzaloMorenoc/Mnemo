from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api_v2 import router, get_current_user, get_jira_ingestion_service, get_integrations_repo


class _User:
    user_id = "u1"


class _FakeIntegrations:
    def __init__(self):
        self.saved = None

    def upsert_jira_config(self, **kw):
        self.saved = kw

    def get_jira_config(self, *, user_id, org_id):
        return {"configured": True, "base_url": "https://acme.atlassian.net",
                "email": "a@b.c", "jql": "issuetype = Bug"}


class _FakeService:
    def ingest_from_pull(self, *, user_id, org_id, project):
        return {"run_id": "r", "ingested": 2, "known": 0, "novel": 2, "skipped": 1}


def _app(integrations, service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[get_integrations_repo] = lambda: integrations
    app.dependency_overrides[get_jira_ingestion_service] = lambda: service
    return TestClient(app)


def test_get_jira_config_omits_token():
    client = _app(_FakeIntegrations(), _FakeService())
    r = client.get("/v2/integrations/jira", params={"org_id": "o1"})
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert "token" not in body


def test_set_jira_config_rejects_http():
    integrations = _FakeIntegrations()
    client = _app(integrations, _FakeService())
    r = client.post("/v2/integrations/jira", json={
        "org_id": "o1", "base_url": "http://acme.atlassian.net",
        "email": "a@b.c", "token": "t", "jql": "issuetype = Bug"})
    assert r.status_code == 400
    assert integrations.saved is None


def test_pull_returns_counts():
    client = _app(_FakeIntegrations(), _FakeService())
    r = client.post("/v2/ingest/jira/pull", json={"org_id": "o1", "project": "p"})
    assert r.status_code == 200
    assert r.json()["skipped"] == 1
