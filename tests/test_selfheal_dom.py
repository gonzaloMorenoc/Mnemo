from bs4 import BeautifulSoup

from src.actions.selfheal.dom import find_element, signature
from src.actions.selfheal.selector import BrokenSelector

_GREEN = """
<html><body>
  <button id="checkout-btn" data-testid="checkout" aria-label="Checkout now">Checkout</button>
  <a href="/x">Home</a>
</body></html>
"""


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def test_find_element_by_css_id():
    el = find_element(_soup(_GREEN), BrokenSelector("css", "#checkout-btn"))
    assert el is not None and el.name == "button"


def test_find_element_by_testid():
    el = find_element(_soup(_GREEN), BrokenSelector("testid", "checkout"))
    assert el is not None and el.get("id") == "checkout-btn"


def test_find_element_by_text():
    el = find_element(_soup(_GREEN), BrokenSelector("text", "Checkout"))
    assert el is not None and el.name == "button"


def test_find_element_none_when_absent():
    assert find_element(_soup(_GREEN), BrokenSelector("css", "#nope")) is None


def test_signature_extracts_stable_attrs():
    el = find_element(_soup(_GREEN), BrokenSelector("css", "#checkout-btn"))
    sig = signature(el)
    assert sig.tag == "button" and sig.role == "button"
    assert sig.text == "Checkout" and sig.testid == "checkout"
    assert sig.aria_label == "Checkout now" and sig.el_id == "checkout-btn"


def test_find_element_by_role_link():
    el = find_element(_soup(_GREEN), BrokenSelector("role", "link"))
    assert el is not None and el.name == "a"


def test_implicit_role_input():
    from src.actions.selfheal.dom import _implicit_role
    assert _implicit_role("input") == "textbox"
