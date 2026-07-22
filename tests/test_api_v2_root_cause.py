from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api_v2 import (router, get_current_user, get_assurance_repo,
                        get_root_cause_analyzer, get_knowledge_proposal_service_optional)


class _User:
    user_id = "u1"


FAM = {"family": {"id": "d1", "title": "T", "status": "open", "occurrence_count": 3,
                  "root_cause": None}, "failures": []}


class _Repo:
    def __init__(self, cached=None):
        FAM["family"]["root_cause"] = cached
        self.saved = None

    def get_family_with_failures(self, *, user_id, defect_id):
        return FAM if defect_id == "d1" else None

    def save_root_cause(self, *, user_id, defect_id, text):
        self.saved = text
        return True


_DEGRADED = {"root_cause": "no determinable", "why_it_happened": "", "how_to_fix": "",
             "suggested_fix_steps": [], "confidence": 0.0, "citations": []}
_GOOD_STRUCT = {"root_cause": "x", "why_it_happened": "", "how_to_fix": "",
                "suggested_fix_steps": [], "confidence": 0.7, "citations": ["failure:fl1"]}


class _Analyzer:
    """El endpoint renderiza el markdown desde el RCA estructurado — analyze() ya NO
    se llama (antes provocaba una 2ª llamada LLM por análisis)."""

    def __init__(self, out="## Causa raíz\nx", structured=None):
        self.struct_calls = 0
        self.out = out
        self._structured = structured

    def analyze_structured(self, family, failures, **kwargs):
        self.struct_calls += 1
        if self._structured is not None:
            return self._structured
        if self.out is None:
            raise RuntimeError("LLM down")
        # non-degraded: return something with confidence>0
        return {**_GOOD_STRUCT}


def _client(repo, analyzer, proposals=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[get_assurance_repo] = lambda: repo
    app.dependency_overrides[get_root_cause_analyzer] = lambda: analyzer
    app.dependency_overrides[get_knowledge_proposal_service_optional] = lambda: proposals
    return TestClient(app)


def test_generates_and_caches():
    repo, analyzer = _Repo(cached=None), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.status_code == 200
    body = r.json()
    assert body["cached"] is False and "Causa raíz" in body["root_cause"]
    assert repo.saved is not None and analyzer.struct_calls == 1  # UNA sola llamada LLM


def test_returns_cache_without_regenerating():
    repo, analyzer = _Repo(cached="## Causa raíz\ncacheado"), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.json()["cached"] is True and analyzer.struct_calls == 0


def test_regenerate_forces_new():
    repo, analyzer = _Repo(cached="viejo"), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause?regenerate=true")
    assert r.json()["cached"] is False and analyzer.struct_calls == 1


def test_hook_leaves_proposal_from_rca():
    """El hook memoria-en-el-flujo: analizar la causa raíz deja una propuesta."""
    repo, analyzer = _Repo(cached=None), _Analyzer()
    proposals = MagicMock()
    r = _client(repo, analyzer, proposals=proposals).post("/v2/defects/d1/root-cause")
    assert r.status_code == 200
    kw = proposals.propose_from_rca.call_args.kwargs
    assert kw["family"]["id"] == "d1"
    assert kw["rca"]["confidence"] == 0.7


def test_hook_error_does_not_break_response():
    repo, analyzer = _Repo(cached=None), _Analyzer()
    proposals = MagicMock()
    proposals.propose_from_rca.side_effect = RuntimeError("db down")
    r = _client(repo, analyzer, proposals=proposals).post("/v2/defects/d1/root-cause")
    assert r.status_code == 200          # el hook es best-effort


def test_hook_not_called_when_cached():
    repo, analyzer = _Repo(cached="## Causa raíz\ncacheado"), _Analyzer()
    proposals = MagicMock()
    _client(repo, analyzer, proposals=proposals).post("/v2/defects/d1/root-cause")
    proposals.propose_from_rca.assert_not_called()


def test_unknown_defect_404():
    r = _client(_Repo(), _Analyzer()).post("/v2/defects/nope/root-cause")
    assert r.status_code == 404


def test_llm_down_503():
    r = _client(_Repo(cached=None), _Analyzer(out=None)).post("/v2/defects/d1/root-cause")
    assert r.status_code == 503


def test_degraded_analysis_returns_503_and_does_not_cache():
    """analyze_structured with confidence==0.0 and no citations → 503, save never called."""
    repo = _Repo(cached=None)
    analyzer = _Analyzer(structured=_DEGRADED)
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.status_code == 503
    assert repo.saved is None


def test_good_structured_result_saves_and_returns_200():
    """analyze_structured with confidence>0 → analyze text is saved, 200 returned."""
    repo = _Repo(cached=None)
    analyzer = _Analyzer(structured=_GOOD_STRUCT)
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.status_code == 200
    assert repo.saved is not None
    assert analyzer.struct_calls == 1
