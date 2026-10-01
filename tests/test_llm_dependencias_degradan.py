"""Sin LLM construible, las dependencias que lo envuelven degradan en vez de dar 500.

get_narrator y get_root_cause_analyzer llamaban a get_llm_provider() sin
protección: con un proveedor mal configurado (o sin ninguno), GET
/assurance/run/{id} daba 500 aunque la narrativa ya sabía degradar a None.
"""
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api_v2 as api_v2
from src import config
from src.security import AuthenticatedUser


def test_narrator_and_rca_build_without_llm(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    monkeypatch.setattr(api_v2, "_narrator", None)
    monkeypatch.setattr(api_v2, "_root_cause_analyzer", None)
    assert api_v2.get_narrator() is not None
    assert api_v2.get_root_cause_analyzer() is not None


def test_assurance_verdict_without_llm_has_no_narrative(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    monkeypatch.setattr(api_v2, "_narrator", None)
    repo = MagicMock()
    repo.get_run_assurance_data.return_value = {
        "run": {"id": "r1"}, "summary": {"ingested": 1}, "families": []}
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: repo
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id="u", email="e@x.com", claims={})
    resp = TestClient(app).get("/v2/assurance/run/r1")
    assert resp.status_code == 200 and resp.json()["narrative"] is None
