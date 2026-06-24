from bs4 import BeautifulSoup

from src.actions.selfheal.locator import robust_locator


def _el(html):
    return BeautifulSoup(html, "html.parser").find(True)


def test_role_with_name_is_best():
    loc, rank = robust_locator(_el("<button>Checkout</button>"))
    assert loc == "getByRole('button', { name: 'Checkout' })" and rank == 4


def test_testid_when_no_accessible_name():
    loc, rank = robust_locator(_el("<div data-testid='cart'></div>"))
    assert loc == "getByTestId('cart')" and rank == 3


def test_text_when_no_role_no_testid():
    loc, rank = robust_locator(_el("<span>Total</span>"))
    assert loc == "getByText('Total', { exact: true })" and rank == 2


def test_id_fallback():
    loc, rank = robust_locator(_el("<div id='x'></div>"))
    assert loc == "locator('#x')" and rank == 1


def test_css_tag_last_resort():
    loc, rank = robust_locator(_el("<section></section>"))
    assert rank == 0 and "section" in loc


def test_escapes_single_quotes():
    loc, _ = robust_locator(_el("<button>It's go</button>"))
    assert "\\'" in loc
