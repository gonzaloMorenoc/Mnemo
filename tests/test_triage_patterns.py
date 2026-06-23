from src.triage.patterns import classify_error


def test_infra_patterns():
    assert "infra" in classify_error("Error", "connect ECONNREFUSED 127.0.0.1:5432")
    assert "infra" in classify_error(None, "net::ERR_CONNECTION_RESET")
    assert "infra" in classify_error(None, "Target page, context or browser has been closed")


def test_locator_patterns():
    assert "locator" in classify_error("TimeoutError", "Timeout 30000ms exceeded waiting for locator")
    assert "locator" in classify_error(None, "locator.click: strict mode violation")
    assert "locator" in classify_error(None, "element is not visible")


def test_assertion_patterns():
    assert "assertion" in classify_error(None, "expect(received).toBe(expected)")
    assert "assertion" in classify_error("AssertionError", "Expected: 5  Received: 4")


def test_no_match_returns_empty():
    assert classify_error(None, "algo salió mal sin patrón conocido") == set()


def test_multiple_categories():
    cats = classify_error("TimeoutError", "expect(locator).toBeVisible() failed waiting for locator")
    assert "locator" in cats and "assertion" in cats


def test_assertion_mentioning_locator_is_not_locator_error():
    # Una aserción de texto que menciona "locator" pero sin frase de fallo de locator
    # NO debe clasificarse como locator (evita misclasificar defectos reales como mantenimiento).
    cats = classify_error(None, "expect(page.locator('x')).toHaveText('foo'): Expected: foo Received: bar")
    assert "assertion" in cats
    assert "locator" not in cats
