from src.triage.tiebreaker import LLMTiebreaker, _build_prompt, parse_category
from src.llm.provider import LLMProvider


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


def test_parse_category_bare_infrastructure_is_none():
    assert parse_category("infrastructure") is None


def test_parse_category_prompt_echo_returns_none():
    # un eco que lista las 4 categorías no es una decisión → None
    assert parse_category("Elige una de: flaky, infra, maintenance, real") is None


def test_build_prompt_includes_active_signals_and_error():
    p = _build_prompt({"error_type": "AssertionError",
                       "signals": [{"name": "assertion_failure", "value": True},
                                   {"name": "infra_error", "value": False}],
                       "rule_applied": "R6_unknown"})
    assert "AssertionError" in p and "assertion_failure" in p
    assert "infra_error" not in p  # inactiva → no se lista


def test_build_prompt_no_signals_says_ninguna():
    assert "ninguna" in _build_prompt({"error_type": "X", "signals": [], "rule_applied": "R6"})


def test_fake_provider_satisfies_protocol():
    assert isinstance(_FakeProvider(resp="x"), LLMProvider)
