from src.assurance.root_cause import RootCauseAnalyzer


class _FakeProvider:
    def __init__(self, out):
        self.out = out
        self.prompt = None

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.out


def test_analyze_calls_provider_and_strips_think():
    p = _FakeProvider("<think>razonando</think>## Causa raíz\nTimeouts de red")
    analyzer = RootCauseAnalyzer(p)
    out = analyzer.analyze({"title": "Timeout", "occurrence_count": 5},
                           [{"test_name": "t", "error_type": "TimeoutException",
                             "message": "m", "trace": "at A.java:1", "project": "p"}])
    assert out == "## Causa raíz\nTimeouts de red"
    assert "Timeout" in p.prompt
