from src.triage.tiebreaker import LLMTiebreaker, parse_category


def test_parse_category_finds_valid():
    assert parse_category("La categoría es real porque hay aserción") == "real"
    assert parse_category("FLAKY: intermitente") == "flaky"
    assert parse_category("Esto es maintenance, la app cambió") == "maintenance"
    assert parse_category("categoría: infra (red caída)") == "infra"


def test_parse_category_earliest_wins():
    # si aparecen varias, gana la primera por posición
    assert parse_category("parece real pero podría ser flaky") == "real"


def test_parse_category_none_when_absent():
    assert parse_category("no estoy seguro") is None
    assert parse_category("") is None
    # palabras que CONTIENEN una categoría pero no son la palabra (word boundary)
    assert parse_category("infrastructure-as-code") is None


class _FakeProvider:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc

    def complete(self, prompt: str) -> str:
        if self._exc:
            raise self._exc
        return self._resp


def test_llm_tiebreaker_valid_returns_category_and_reason():
    tb = LLMTiebreaker(provider=_FakeProvider(resp="Categoría: real. Razón: aserción que falla."))
    result = tb.resolve({"error_type": "AssertionError", "signals": [], "rule_applied": "R6_unknown"})
    assert result is not None
    cat, reason = result
    assert cat == "real" and "aserción" in reason.lower()


def test_llm_tiebreaker_unparseable_returns_none():
    tb = LLMTiebreaker(provider=_FakeProvider(resp="No puedo determinarlo"))
    assert tb.resolve({"error_type": "X", "signals": []}) is None


def test_llm_tiebreaker_exception_returns_none():
    tb = LLMTiebreaker(provider=_FakeProvider(exc=RuntimeError("LLM caído")))
    assert tb.resolve({"error_type": "X", "signals": []}) is None
