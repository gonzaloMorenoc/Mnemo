from bs4 import BeautifulSoup

from src.actions.selfheal.candidates import find_candidates, rank
from src.actions.selfheal.dom import ElementSignature

_FAILURE = """
<html><body>
  <button id="checkout-button-v2">Checkout</button>
  <button id="cancel">Cancel</button>
</body></html>
"""


def _sig():
    return ElementSignature(tag="button", role="button", text="Checkout",
                            testid=None, aria_label=None, el_id="checkout-btn")


def test_finds_renamed_element():
    soup = BeautifulSoup(_FAILURE, "html.parser")
    cands = find_candidates(soup, _sig())
    assert any(c.get_text(strip=True) == "Checkout" for c in cands)


def test_ranks_semantic_match_first():
    soup = BeautifulSoup(_FAILURE, "html.parser")
    ranked = rank(find_candidates(soup, _sig()), _sig())
    assert ranked[0].locator == "getByRole('button', { name: 'Checkout' })"
    assert ranked[0].score > ranked[1].score          # Checkout supera a Cancel
    assert "texto" in ranked[0].why or "role" in ranked[0].why


def test_rank_empty_when_no_candidates():
    soup = BeautifulSoup("<html><body><p>nada</p></body></html>", "html.parser")
    assert rank(find_candidates(soup, _sig()), _sig()) == []
