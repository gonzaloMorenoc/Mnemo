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


class _Analyzer:
    def __init__(self, out="## Causa raíz\nx"):
        self.calls = 0
        self.out = out

    def analyze(self, family, failures):
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


def test_empty_analysis_returns_503_and_does_not_cache():
    repo, analyzer = _Repo(cached=None), _Analyzer(out="   ")
    r = _client(repo, analyzer).post("/v2/defects/d1/root-cause")
    assert r.status_code == 503
    assert repo.saved is None
