from src.assurance.narrator import Narrator, LocalNarrator


def test_local_narrator_lazy():
    n = LocalNarrator()
    assert hasattr(n, "summarize")
    assert n._llm is None


def test_fake_narrator_satisfies_protocol():
    class Fake:
        def summarize(self, verdict: dict) -> str:
            return "ok"

    def use(n: Narrator) -> str:
        return n.summarize({})

    assert use(Fake()) == "ok"
