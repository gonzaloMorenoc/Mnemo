from src.actions.selfheal.selector import BrokenSelector, parse_broken_selector


def test_parse_css():
    b = parse_broken_selector("waiting for locator('#checkout-btn')")
    assert b == BrokenSelector(kind="css", value="#checkout-btn")


def test_parse_testid():
    b = parse_broken_selector("Timeout waiting for getByTestId('checkout')")
    assert b.kind == "testid" and b.value == "checkout"


def test_parse_text():
    b = parse_broken_selector("waiting for getByText('Checkout')")
    assert b.kind == "text" and b.value == "Checkout"


def test_parse_role_with_name():
    b = parse_broken_selector("waiting for getByRole('button', { name: 'Checkout' })")
    assert b.kind == "role" and b.value == "button" and b.name == "Checkout"


def test_parse_searches_trace_too():
    b = parse_broken_selector("Timeout", trace="...\n  at locator('.submit')\n...")
    assert b.kind == "css" and b.value == ".submit"


def test_parse_prefers_error_message_over_trace():
    # regresión: el locator que falló está en el mensaje de error; el trace puede
    # contener locators de pasos anteriores que NO deben capturarse.
    b = parse_broken_selector(
        "TimeoutError: waiting for getByRole('button', { name: 'Pay' })",
        trace="  at checkout\n  getByTestId('old-nav-btn')\n",
    )
    assert b.kind == "role" and b.value == "button" and b.name == "Pay"


def test_parse_none_when_unrecognized():
    assert parse_broken_selector("some unrelated error", trace=None) is None
