"""Auditoría 2026-11-23 #2: `/v2/test-plan/generate` es `async def` y ejecutaba el
trabajo bloqueante (embedding, BD, Jira, LLM) DENTRO del event loop: mientras duraba,
no respondía nadie (ni `/v2/health`). El trabajo pesado debe ir al threadpool."""
import asyncio
import time
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI

import src.api_v2 as api_v2
from src.security import AuthenticatedUser

_SLOW_SECONDS = 0.6
_HEAD_START_SECONDS = 0.1


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(api_v2.router)
    app.dependency_overrides[api_v2.get_current_user] = lambda: AuthenticatedUser(
        user_id="u-1", email="t@e.com", claims={})
    app.dependency_overrides[api_v2.get_knowledge_repo] = lambda: MagicMock()
    app.dependency_overrides[api_v2.get_assurance_repo] = lambda: MagicMock()
    app.dependency_overrides[api_v2.get_integrations_repo] = lambda: MagicMock()
    app.dependency_overrides[api_v2.get_embedder] = lambda: MagicMock()
    return app


def _slow(**_kw):
    time.sleep(_SLOW_SECONDS)          # bloqueante, como el embedding/LLM/Jira reales
    return {"summary": "s", "cases": [], "citations": []}


async def _race(form: dict) -> tuple:
    transport = httpx.ASGITransport(app=_app())
    finished = {}
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        async def plan():
            r = await c.post("/v2/test-plan/generate", data=form)
            finished["plan"] = time.monotonic()
            return r

        async def health():
            await asyncio.sleep(_HEAD_START_SECONDS)   # que el plan ya esté en curso
            r = await c.get("/v2/health")
            finished["health"] = time.monotonic()
            return r

        rp, rh = await asyncio.gather(plan(), health())
    return rp, rh, finished


def test_generate_test_plan_no_bloquea_el_event_loop():
    with patch.object(api_v2, "generate_test_plan", side_effect=_slow):
        rp, rh, finished = asyncio.run(_race({"org_id": "o-1", "hu_text": "Como usuario quiero pagar"}))
    assert rp.status_code == 200, rp.text
    assert rh.status_code == 200
    # /health contesta MIENTRAS el plan sigue trabajando, no al acabar
    assert finished["health"] < finished["plan"]


def test_la_lectura_de_jira_tampoco_bloquea_el_event_loop():
    def _slow_jira(**_kw):
        time.sleep(_SLOW_SECONDS)
        return "HU desde Jira"

    with patch.object(api_v2, "hu_text_from_jira", side_effect=_slow_jira), \
         patch.object(api_v2, "generate_test_plan", return_value={"citations": []}):
        rp, rh, finished = asyncio.run(_race({"org_id": "o-1", "jira_url": "https://j/browse/A-1"}))
    assert rp.status_code == 200, rp.text
    assert finished["health"] < finished["plan"]
