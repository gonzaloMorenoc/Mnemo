from src.assurance.narrator import LLMNarrator, Narrator


class _FakeProvider:
    def __init__(self, out):
        self.out = out
        self.prompt = None

    def complete(self, prompt: str) -> str:
        self.prompt = prompt
        return self.out


def test_llmnarrator_is_narrator():
    assert isinstance(LLMNarrator(_FakeProvider("x")), Narrator)


def test_summarize_uses_provider_and_strips_think():
    p = _FakeProvider("<think>...</think>Run estable, 0 nuevos.")
    n = LLMNarrator(p)
    out = n.summarize({"known": 3, "novel": 0, "risk": "ok", "top_families": []})
    assert out == "Run estable, 0 nuevos."
    assert "3 fallos conocidos" in p.prompt and "0 nuevos" in p.prompt
