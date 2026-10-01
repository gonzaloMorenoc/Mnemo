"""Pares de referencia para calibrar la fusión de familias (decide_match).

Cada texto sigue la receta de la ingesta: f"{error_type} {message}". Solo importa
lo que la firma NO normaliza (números, UUIDs, hex y rutas ya los iguala
src/defects/fingerprint.py): si dos fallos llegan aquí es porque cambian textos
—un selector, un host, un valor entre comillas, la redacción del framework—.

MISMO: el mismo defecto con el mensaje variado → deben fusionarse.
DISTINTO: defectos distintos con la misma forma → NO deben fusionarse.
Los dos primeros DISTINTO salen de prod (Demo MTP, 30-sep): estaban a 0,845.
"""

MISMO = [
    ("TimeoutError Timeout exceeded waiting for selector [data-testid=btn-pagar]",
     "TimeoutError Timeout exceeded while waiting for selector [data-testid=btn-pagar] to be visible"),
    ("AssertionError expected total 'Total: 84,15 €' but got 'Total: 99,00 €'",
     "AssertionError expected total 'Total: 12,50 €' but got 'Total: 27,35 €'"),
    ("ConnectionError connect ECONNREFUSED servicio-facturas.staging",
     "ConnectionError connect ECONNREFUSED servicio-facturas.staging.internal"),
    ("NoSuchElementError locator not found: #btn-finalizar-compra",
     "NoSuchElementError Unable to locate element: #btn-finalizar-compra"),
    ("AssertionError expected status 'confirmado' but got 'pendiente'",
     "AssertionError expected order status to be 'confirmado', received 'pendiente'"),
    ("Error expect(locator).toHaveText(expected) Expected: 'Pedido confirmado' Received: 'Pedido pendiente'",
     "Error expect(locator).toHaveText(expected) failed Expected string: 'Pedido confirmado' Received string: 'Pedido pendiente'"),
    ("AssertionError el saldo disponible no se actualiza tras la transferencia",
     "AssertionError el saldo disponible no se ha actualizado después de la transferencia"),
    ("TimeoutError page.goto: Timeout exceeded navigating to https://tienda.staging/checkout",
     "TimeoutError page.goto: Timeout exceeded navigating to https://tienda.staging/checkout?step=pago"),
    ("HTTPError 503 Service Unavailable from api-pagos.staging /v1/cobros",
     "HTTPError 503 Service Unavailable returned by api-pagos.staging for /v1/cobros"),
    ("AssertionError expected email to be sent to 'comprador@test.com'",
     "AssertionError expected email to be sent to 'otro.comprador@test.com'"),
]

DISTINTO = [
    ("ConnectionError connect ECONNREFUSED servicio-facturas.staging",
     "ConnectionError connect ECONNREFUSED core-bancario.staging"),
    ("TimeoutError Timeout exceeded waiting for selector iframe[name=3ds-challenge]",
     "TimeoutError Timeout exceeded waiting for selector [data-testid=btn-guardar-perfil]"),
    ("AssertionError expected total 'Total: 84,15 €' but got 'Total: 99,00 €'",
     "AssertionError expected stock 'Disponible' but got 'Agotado'"),
    ("NoSuchElementError locator not found: #btn-finalizar-compra",
     "NoSuchElementError locator not found: #enlace-recuperar-contrasena"),
    ("AssertionError expected status 'confirmado' but got 'pendiente'",
     "AssertionError expected IBAN validation error but form was accepted"),
    ("HTTPError 503 Service Unavailable from api-pagos.staging /v1/cobros",
     "HTTPError 401 Unauthorized from api-pagos.staging /v1/reembolsos"),
    ("AssertionError el saldo disponible no se actualiza tras la transferencia",
     "AssertionError el segundo factor no se exige tras el login"),
    ("TimeoutError page.goto: Timeout exceeded navigating to https://tienda.staging/checkout",
     "TimeoutError page.goto: Timeout exceeded navigating to https://intranet.staging/nominas"),
    ("Error expect(locator).toHaveText(expected) Expected: 'Pedido confirmado' Received: 'Pedido pendiente'",
     "Error expect(locator).toHaveText(expected) Expected: 'Cupón aplicado' Received: 'Cupón no válido'"),
    ("AssertionError expected email to be sent to 'comprador@test.com'",
     "AssertionError expected push notification to be sent to the manager"),
]
