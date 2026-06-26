from src.ai.briefing import build_run_data, generate_briefing


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _Boom:
    def complete(self, prompt): raise RuntimeError("down")


_ASSURANCE = {"run": {"id": "r1", "project": "checkout", "source": "ci"},
              "summary": {"ingested": 5, "novel": 1},
              "families": [{"id": "f1", "title": "checkout 500", "occurrence_count": 3, "run_count": 2}]}
_CERT = {"verdict": "apto-con-reservas", "risk_score": 0.4, "canonical_json": "{\"self_eval\": {\"confidence\": \"low\"}}"}
_ACTIONS = [{"id": "a1", "kind": "self_heal", "summary": "Reparación IA: checkout.spec.ts"}]


def test_build_run_data_has_citable_ids_and_facts():
    rd = build_run_data(assurance=_ASSURANCE, certificate=_CERT, actions=_ACTIONS)
    ids = {c["id"] for c in rd["context"]}
    assert "run" in ids and "cert" in ids and "family:f1" in ids and "action:a1" in ids
    assert rd["facts"]["verdict"] == "apto-con-reservas"


def test_generate_briefing_with_citations():
    rd = build_run_data(assurance=_ASSURANCE, certificate=_CERT, actions=_ACTIONS)
    out = '{"summary":"checkout falla 1 novel","verdict_line":"apto-con-reservas","highlights":["1 defecto real"],"recommendation":"revisar el parche","citations":["family:f1","action:a1"]}'
    b = generate_briefing(run_data=rd, provider=_Provider(out))
    assert "checkout" in b["summary"] and b["citations"] == ["family:f1", "action:a1"]
    assert isinstance(b["highlights"], list) and b["recommendation"]


def test_generate_briefing_degrades_to_template_without_llm():
    rd = build_run_data(assurance=_ASSURANCE, certificate=_CERT, actions=_ACTIONS)
    b = generate_briefing(run_data=rd, provider=_Boom())
    assert "apto-con-reservas" in b["verdict_line"]      # plantilla con el veredicto
    assert b["summary"]                                   # no vacío
    assert "family:f1" in b["citations"] or "run" in b["citations"]


def test_generate_briefing_normalizes_types():
    rd = build_run_data(assurance=_ASSURANCE, certificate=None, actions=[])
    b = generate_briefing(run_data=rd, provider=_Provider('{"summary":123,"citations":"x"}'))
    assert isinstance(b["summary"], str) and isinstance(b["citations"], list) and isinstance(b["highlights"], list)
