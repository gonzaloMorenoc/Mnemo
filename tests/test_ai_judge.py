from src.ai.judge import judge_output, compute_ai_eval


class _Provider:
    def __init__(self, out): self._out = out
    def complete(self, prompt): return self._out


class _SpyProvider:
    """Captura el prompt que recibe y devuelve una respuesta fija."""
    def __init__(self, out):
        self._out = out
        self.captured_prompt: str = ""

    def complete(self, prompt: str) -> str:
        self.captured_prompt = prompt
        return self._out


def test_judge_returns_scores():
    prov = _Provider('{"faithfulness": 0.8, "groundedness": 0.7}')
    out = judge_output(claim="es flaky", evidence=[{"id": "e1", "content": "retry pasó"}], provider=prov)
    assert out == {"faithfulness": 0.8, "groundedness": 0.7}


def test_compute_ai_eval_none_when_no_llm_assisted():
    verdicts = [{"category": "flaky", "llm_assisted": False, "evidence_bundle": {}}]
    assert compute_ai_eval(verdicts=verdicts, created_at="t", provider=_Provider("{}")) is None


def test_compute_ai_eval_aggregates_llm_assisted():
    prov = _Provider('{"faithfulness": 0.6, "groundedness": 0.6}')
    verdicts = [{"category": "real", "llm_assisted": True, "evidence_bundle": {"x": 1}, "rule_applied": "R6_ambiguous"}]
    out = compute_ai_eval(verdicts=verdicts, created_at="t", provider=prov, judge_model="m")
    assert out["method"] == "llm_judge" and out["n"] == 1
    assert out["faithfulness"] == 0.6 and out["judge_model"] == "m" and out["evaluated_at"] == "t"


def test_compute_ai_eval_none_when_provider_missing():
    verdicts = [{"category": "real", "llm_assisted": True, "evidence_bundle": {}}]
    # provider que lanza → judge None para todos → ai_eval None
    class _Boom:
        def complete(self, p): raise RuntimeError("down")
    assert compute_ai_eval(verdicts=verdicts, created_at="t", provider=_Boom()) is None


def test_compute_ai_eval_evidence_serialized_as_json():
    """La evidencia llega al juez como JSON (comillas dobles), no como repr de Python."""
    spy = _SpyProvider('{"faithfulness": 0.9, "groundedness": 0.8}')
    verdicts = [
        {
            "category": "flaky",
            "llm_assisted": True,
            "rule_applied": "R6_ambiguous",
            "evidence_bundle": {
                "signals": [{"name": "assertion_failure", "value": True}],
                "lineage_projects": ["a", "b"],
            },
        }
    ]
    out = compute_ai_eval(verdicts=verdicts, created_at="t", provider=spy, judge_model="m")
    assert out is not None
    # El prompt debe contener JSON válido con comillas dobles (no repr de Python)
    assert '"name": "assertion_failure"' in spy.captured_prompt
    assert '["a", "b"]' in spy.captured_prompt
