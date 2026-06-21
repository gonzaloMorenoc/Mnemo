from src.llm.provider import LLMProvider


class _Fake:
    def complete(self, prompt: str) -> str:
        return "ok"


def test_fake_satisfies_protocol():
    assert isinstance(_Fake(), LLMProvider)


def test_non_provider_rejected():
    assert not isinstance(object(), LLMProvider)
