from src.assurance.root_cause import RootCauseAnalyzer


class _FakeProvider:
    def __init__(self, out):
        self.out = out
        self.prompt = None

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.out


def test_analyze_calls_provider_and_returns_structured_markdown():
    # analyze() now returns structured markdown from generate_structured (JSON → markdown)
    json_out = '{"root_cause":"Timeouts de red","why_it_happened":"red lenta","how_to_fix":"retry","suggested_fix_steps":["paso1"],"confidence":0.9,"citations":[]}'
    p = _FakeProvider(json_out)
    analyzer = RootCauseAnalyzer(p)
    out = analyzer.analyze({"title": "Timeout", "occurrence_count": 5},
                           [{"test_name": "t", "error_type": "TimeoutException",
                             "message": "m", "trace": "at A.java:1", "project": "p"}])
    assert "## Causa raíz" in out
    assert "Timeouts de red" in out
    assert "Timeout" in p.prompt
