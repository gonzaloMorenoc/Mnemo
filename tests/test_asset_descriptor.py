"""El texto que se embebe de un test: lo que dice QUÉ prueba, no su sintaxis.

Medido en Demo MTP (30-sep): embebiendo el código entero, los `import` y la
sintaxis dominaban y la regla «un cupón se aplica una sola vez» quedaba más cerca
de reembolsos.test.ts que de cupones.spec.ts. Con ruta + títulos + comentarios,
5 de 6 reglas cubiertas encuentran su test correcto y ninguna sin test pasa el corte.
"""
from src.repo_ingest.descriptor import asset_descriptor

_PLAYWRIGHT = """import { test, expect } from '@playwright/test';

// OJO: staging apaga el servicio de facturas a las 20:00
test('un cupon se aplica una sola vez aunque el pago se reintente', async ({ page }) => {
  await page.goto('/checkout?cupon=DEMO15');
  expect(total).toBe('85,00 EUR');
});
"""


def test_keeps_path_titles_and_comments_and_drops_the_code():
    d = asset_descriptor("tests/tienda/cupones.spec.ts", _PLAYWRIGHT)
    assert "tienda cupones" in d
    assert "un cupon se aplica una sola vez aunque el pago se reintente" in d
    assert "staging apaga el servicio de facturas" in d
    assert "import" not in d and "page.goto" not in d


def test_supports_describe_it_and_cypress_style():
    src = "describe('login', () => {\n  it(\"usuario registrado inicia sesión\", () => {})\n})"
    d = asset_descriptor("tests/login.cy.ts", src)
    assert "login" in d and "usuario registrado inicia sesión" in d


def test_supports_pytest_function_names():
    src = "def test_reembolso_no_supera_el_importe_capturado():\n    assert True\n"
    d = asset_descriptor("tests/test_reembolsos.py", src)
    assert "reembolso no supera el importe capturado" in d


def test_falls_back_to_content_when_no_titles_are_found():
    # Un fichero sin títulos reconocibles (helpers, page objects) no se queda sin
    # vector: se embebe su contenido como antes.
    src = "export const selectores = { pagar: '#pagar' };"
    assert asset_descriptor("tests/helpers.ts", src) == src


def test_is_capped_like_the_stored_content():
    titles = "\n".join(f"test('caso {i}', () => {{}})" for i in range(2000))
    assert len(asset_descriptor("tests/x.spec.ts", titles)) <= 8000


def test_css_selectors_and_urls_are_not_comments():
    src = ("test('pagar', async ({ page }) => {\n"
           "  await page.goto('https://tienda.staging/checkout');\n"
           "  await page.click('#pagar');  // reintento forzado\n"
           "});")
    d = asset_descriptor("tests/pago.spec.ts", src)
    assert "reintento forzado" in d
    assert "pagar')" not in d and "tienda.staging" not in d
