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


def test_degrades_when_old_element_deleted():
    # el botón viejo no existe en el DOM rojo; solo hay botones sin relación → no curar
    ctx = _ctx(error_message="waiting for locator('#buy-btn')",
               green_dom="<button id='buy-btn'>Buy Now</button>",
               failure_dom="<button>Home</button><button>Help</button>")
    assert SelfHealActuator().propose({}, ctx) is None


def test_degrades_id_only_signature_no_content():
    # un div sin texto/role/testid → ninguna señal de contenido → no curar
    ctx = _ctx(error_message="waiting for locator('#modal')",
               green_dom="<div id='modal'></div>",
               failure_dom="<div id='m2'></div><div id='m3'></div>")
    assert SelfHealActuator().propose({}, ctx) is None


def test_exact_text_beats_partial_cross_tag():
    ctx = _ctx(error_message="waiting for locator('#save-btn')",
               green_dom="<button id='save-btn'>Save</button>",
               failure_dom="<span>Save</span><button>Save Draft and Exit</button>")
    p = SelfHealActuator().propose({}, ctx)
    assert p is not None
    assert "Save Draft" not in p.payload["suggested_locator"]   # el parcial NO gana


def test_degrades_ambiguous_locator():
    ctx = _ctx(error_message="waiting for locator('#save-btn')",
               green_dom="<button id='save-btn'>Save</button>",
               failure_dom="<button>Save</button><button>Save</button>")
    assert SelfHealActuator().propose({}, ctx) is None   # 2 elementos idénticos → ambiguo → degrade
