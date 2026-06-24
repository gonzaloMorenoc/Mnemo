from unittest.mock import MagicMock

from src.actions.selfheal.selfheal import SelfHealActuator

_GREEN = "<button id='checkout-btn'>Checkout</button>"
_FAILURE = "<button id='checkout-v2'>Checkout</button><button id='c'>Cancel</button>"


def _ctx(**over):
    base = {"error_message": "waiting for locator('#checkout-btn')", "trace": None,
            "green_dom": _GREEN, "failure_dom": _FAILURE}
    base.update(over)
    return base


def test_e2e_renamed_id_to_getbyrole():
    p = SelfHealActuator().propose({"category": "maintenance"}, _ctx())
    assert p is not None and p.kind == "self_heal"
    assert p.payload["suggested_locator"] == "getByRole('button', { name: 'Checkout' })"
    assert "checkout-btn" in p.payload["broken_locator"]
    assert p.payload["candidates"] and "robusto" in p.payload["reasoning"].lower()


def test_degrades_no_dom():
    assert SelfHealActuator().propose({}, _ctx(green_dom=None, failure_dom=None)) is None


def test_degrades_unparseable_selector():
    assert SelfHealActuator().propose({}, _ctx(error_message="boom genérico")) is None


def test_degrades_old_element_not_in_green():
    assert SelfHealActuator().propose({}, _ctx(error_message="locator('#missing')")) is None


def test_uses_explainer_when_present():
    explainer = MagicMock()
    explainer.explain.return_value = "Razón del LLM."
    p = SelfHealActuator(explainer=explainer).propose({}, _ctx())
    assert p.payload["reasoning"] == "Razón del LLM."


def test_degrades_explainer_raises_to_template():
    explainer = MagicMock()
    explainer.explain.side_effect = RuntimeError("LLM caído")
    p = SelfHealActuator(explainer=explainer).propose({}, _ctx())
    assert "robusto" in p.payload["reasoning"].lower()


def test_broken_locator_role_renders_canonically():
    ctx = _ctx(error_message="waiting for getByRole('button', { name: 'Checkout' })")
    p = SelfHealActuator().propose({}, ctx)
    assert p is not None
    assert p.payload["broken_locator"] == "getByRole('button', { name: 'Checkout' })"
