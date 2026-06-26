from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api_v2 import router, get_current_user, get_assurance_repo, get_root_cause_analyzer


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
    def __init__(self, out="## Causa raíz\nx", structured=None):
        self.calls = 0
        self.save_calls = 0
        self.out = out
        # structured: None → derive from out; explicit dict → return that
        self._structured = structured

    def analyze_structured(self, family, failures, **kwargs):
        if self._structured is not None:
            return self._structured
        if self.out is None:
            raise RuntimeError("LLM down")
        # non-degraded: return something with confidence>0
        return {**_GOOD_STRUCT}

    def analyze(self, family, failures, **kwargs):
        self.calls += 1
        if self.out is None:
            raise RuntimeError("LLM down")
        return self.out


def _client(repo, analyzer):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[get_assurance_repo] = lambda: repo
    app.dependency_overrides[get_root_cause_analyzer] = lambda: analyzer
    return TestClient(app)


def test_generates_and_caches():
    repo, analyzer = _Repo(cached=None), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.status_code == 200
    body = r.json()
    assert body["cached"] is False and "Causa raíz" in body["root_cause"]
    assert repo.saved is not None and analyzer.calls == 1


def test_returns_cache_without_regenerating():
    repo, analyzer = _Repo(cached="## Causa raíz\ncacheado"), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.json()["cached"] is True and analyzer.calls == 0


def test_regenerate_forces_new():
    repo, analyzer = _Repo(cached="viejo"), _Analyzer()
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause?regenerate=true")
    assert r.json()["cached"] is False and analyzer.calls == 1


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
    assert analyzer.calls == 1
