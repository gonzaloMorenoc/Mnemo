"""Datos de la demo: qué falla en cada proyecto y cuándo corrió cada run.

Separado del motor de siembra a propósito: este es el fichero que se toca para
cambiar lo que se ve en la demo. Los fallos imitan incidencias reales de QA —un
timeout de pasarela, un selector que cambió, un 500 en un endpoint— porque el
Defect DNA de la demo tiene que leerse como el de un cliente de verdad.

Dos reglas al editarlo:
  - Cada fallo habla de SU proyecto (banca-movil no falla en «añadir al carrito»).
  - Ninguna firma se repite: el fingerprint es (error_type, mensaje normalizado,
    top frame del trace), así que dos fallos con la misma terna mergearían en una
    única familia y el Defect DNA perdería variedad.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.ci.models import CiTestResult

PROYECTOS = ("checkout-suite", "tienda-online", "banca-movil",
             "portal-clientes", "intranet-rrhh", "api-pagos")


@dataclass(frozen=True)
class RunSpec:
    """Un run del calendario. `days_ago=0` es hoy; el orden cronológico lo fija
    ese campo, no la posición en la lista."""
    project: str
    commit: str
    days_ago: int
    n_pass: int
    failure_keys: Tuple[str, ...] = field(default_factory=tuple)
    # Tests del catálogo que en este run PASAN, con el DOM que tenían entonces.
    # Es el "pasado verde" que la regla R3 necesita para poder decir que un
    # localizador se rompió (y no que el test es simplemente nuevo).
    green_keys: Tuple[str, ...] = field(default_factory=tuple)


def _fail(name: str, *, error_type: str, message: str, trace: str,
          file: str, line: int, dom: Optional[str] = None) -> CiTestResult:
    return CiTestResult(test_name=name, status="fail", error_type=error_type,
                        message=message, trace=trace, file=file, line=line, dom=dom)


FAILURE_CATALOG: Dict[str, List[CiTestResult]] = {
    "checkout-suite": [
        _fail("test_aplicar_cupon_descuento",
              error_type="AssertionError",
              message="expected total 84.15 but got 99.00",
              trace="at CouponService.apply (coupon.service.ts:73)",
              file="tests/checkout/cupones.spec.ts", line=73),
        _fail("test_pago_tarjeta_3ds_redirige",
              error_type="TimeoutError",
              message="Timeout 20000ms exceeded waiting for selector iframe[name=3ds-challenge]",
              trace="at ThreeDSFrame.waitForReady (threeds.ts:41)",
              file="tests/checkout/pago.spec.ts", line=41,
              dom='<div class="pago"><iframe name="3ds-frame" src="/3ds"></iframe></div>'),
        _fail("test_boton_finalizar_compra_visible",
              error_type="NoSuchElementError",
              message="locator not found: #btn-finalizar-compra",
              trace="at CheckoutPage.finalizar (checkout.page.ts:118)",
              file="tests/checkout/checkout.spec.ts", line=118,
              dom='<div class="acciones"><button id="finalizar">Finalizar compra</button></div>'),
        _fail("test_stock_reservado_al_pagar",
              error_type="AssertionError",
              message="expected stock reserved for 15 minutes but reservation expired",
              trace="at StockService.reserve (stock.service.ts:206)",
              file="tests/checkout/stock.spec.ts", line=206),
        _fail("test_email_confirmacion_pedido",
              error_type="AssertionError",
              message="expected confirmation email queued but the outbox was empty",
              trace="at MailClient.send (mail.client.ts:52)",
              file="tests/checkout/notificaciones.spec.ts", line=52),
    ],
    "tienda-online": [
        _fail("test_buscador_devuelve_resultados_relevantes",
              error_type="AssertionError",
              message="expected first result to match query but ranking changed",
              trace="at SearchRanking.sort (ranking.ts:129)",
              file="tests/catalogo/buscador.spec.ts", line=129),
        _fail("test_filtro_categoria_persiste_al_paginar",
              error_type="AssertionError",
              message="expected filter 'calzado' to persist but query param was dropped",
              trace="at CatalogFilters.paginate (filters.ts:88)",
              file="tests/catalogo/filtros.spec.ts", line=88),
        _fail("test_ficha_producto_carga_galeria",
              error_type="TimeoutError",
              message="Timeout 10000ms exceeded waiting for selector img.gallery-main",
              trace="at Gallery.waitForImages (gallery.ts:34)",
              file="tests/catalogo/ficha.spec.ts", line=34,
              dom='<div class="ficha"><img class="galeria-principal" src="/p/1.jpg"/></div>'),
        _fail("test_anadir_al_carrito_actualiza_contador",
              error_type="NoSuchElementError",
              message="locator not found: span.cart-count",
              trace="at CartWidget.count (cart.widget.ts:22)",
              file="tests/catalogo/carrito.spec.ts", line=22,
              dom='<div class="cart"><span class="contador-carrito">2</span></div>'),
        _fail("test_valoraciones_ordenadas_por_fecha",
              error_type="AssertionError",
              message="expected reviews sorted desc by date but order was random",
              trace="at ReviewList.render (reviews.ts:64)",
              file="tests/catalogo/valoraciones.spec.ts", line=64),
    ],
    "banca-movil": [
        _fail("test_transferencia_inmediata_confirma",
              error_type="AssertionError",
              message="expected confirmation code but got empty response",
              trace="at TransferService.confirm (transfer.service.ts:142)",
              file="tests/transferencias.spec.ts", line=142),
        _fail("test_login_biometrico_fallback_pin",
              error_type="TimeoutError",
              message="Timeout 15000ms exceeded waiting for selector [data-testid=biometric-prompt]",
              trace="at BiometricPrompt.await (biometric.ts:63)",
              file="tests/acceso.spec.ts", line=63,
              dom='<div class="acceso"><div data-testid="prompt-biometrico">Usa tu huella</div></div>'),
        _fail("test_saldo_disponible_tras_operacion",
              error_type="AssertionError",
              message="expected balance 1240.50 but got 1340.50",
              trace="at AccountBalance.refresh (balance.ts:97)",
              file="tests/cuentas.spec.ts", line=97),
        _fail("test_listado_movimientos_scroll_infinito",
              error_type="TimeoutError",
              message="Timeout 12000ms exceeded waiting for selector li.movimiento:nth-child(21)",
              trace="at MovementsList.loadMore (movements.ts:155)",
              file="tests/movimientos.spec.ts", line=155,
              dom='<ul class="movimientos"><li class="mov-item">Compra</li></ul>'),
        _fail("test_alta_beneficiario_valida_iban",
              error_type="ValidationError",
              message="expected IBAN checksum rejection but form accepted the value",
              trace="at expect(validator.check(iban)).toBe(false) (iban.validator.ts:29)",
              file="tests/beneficiarios.spec.ts", line=29),
    ],
    "portal-clientes": [
        _fail("test_descarga_factura_pdf",
              error_type="AssertionError",
              message="expected content-type application/pdf but got text/html",
              trace="at InvoiceDownload.fetch (invoice.ts:81)",
              file="tests/facturas.spec.ts", line=81),
        _fail("test_recuperar_contrasena_envia_correo",
              error_type="AssertionError",
              message="expected reset link in the email body but none was found",
              trace="at NotificationsClient.post (notifications.client.ts:47)",
              file="tests/acceso/recuperar.spec.ts", line=47),
        _fail("test_actualizar_datos_perfil",
              error_type="NoSuchElementError",
              message="locator not found: input[name=telefono_contacto]",
              trace="at ProfileForm.fill (profile.form.ts:58)",
              file="tests/perfil.spec.ts", line=58,
              dom='<form id="perfil"><input name="telefono"/><button>Guardar</button></form>'),
        _fail("test_historial_pedidos_pagina_correctamente",
              error_type="AssertionError",
              message="expected 20 orders per page but received 50",
              trace="at OrderHistory.paginate (orders.ts:112)",
              file="tests/pedidos.spec.ts", line=112),
        _fail("test_cerrar_sesion_invalida_token",
              error_type="AssertionError",
              message="expected 401 after logout but token was still accepted",
              trace="at SessionGuard.verify (session.guard.ts:36)",
              file="tests/acceso/sesion.spec.ts", line=36),
    ],
    "intranet-rrhh": [
        _fail("test_solicitud_vacaciones_calcula_dias",
              error_type="AssertionError",
              message="expected 12 working days but computed 14 including holidays",
              trace="at HolidayCalculator.workingDays (holidays.ts:74)",
              file="tests/vacaciones.spec.py", line=74),
        _fail("test_fichaje_entrada_registra_hora",
              error_type="TimeoutError",
              message="Timeout 8000ms exceeded waiting for selector .toast-confirmacion",
              trace="at ClockIn.confirm (clockin.ts:39)",
              file="tests/fichaje.spec.py", line=39,
              dom='<div class="fichaje"><div class="aviso-confirmacion">Entrada registrada</div></div>'),
        _fail("test_descarga_nomina_mes_actual",
              error_type="AssertionError",
              message="expected download allowed for own payslip but got 403",
              trace="at PayslipController.download (payslip.py:88)",
              file="tests/nominas.spec.py", line=88),
        _fail("test_organigrama_muestra_responsable",
              error_type="NoSuchElementError",
              message="locator not found: div.org-chart-manager",
              trace="at OrgChart.manager (orgchart.ts:51)",
              file="tests/organigrama.spec.py", line=51,
              dom='<div class="org-chart"><div class="responsable">Ana Ruiz</div></div>'),
        _fail("test_aprobacion_gasto_notifica_al_manager",
              error_type="AssertionError",
              message="expected the manager to be notified but no approval was created",
              trace="at ApprovalsQueue.publish (approvals.py:143)",
              file="tests/gastos.spec.py", line=143),
    ],
    "api-pagos": [
        _fail("test_pasarela_responde_bajo_carga",
              error_type="TimeoutError",
              message="ETIMEDOUT waiting for gateway response after 30000ms",
              trace="at PaymentGateway.charge (gateway.ts:210)",
              file="tests/pasarela.spec.ts", line=210),
        _fail("test_reembolso_parcial_actualiza_importe",
              error_type="AssertionError",
              message="expected refunded amount 25.00 but got 0.00",
              trace="at RefundService.partial (refund.service.ts:96)",
              file="tests/reembolsos.spec.ts", line=96),
        _fail("test_webhook_reintenta_ante_error_5xx",
              error_type="AssertionError",
              message="expected 3 delivery attempts but only 1 was recorded",
              trace="at WebhookDispatcher.retry (dispatcher.ts:187)",
              file="tests/webhooks.spec.ts", line=187),
        _fail("test_idempotencia_cobro_duplicado",
              error_type="AssertionError",
              message="expected single charge for repeated idempotency key but got two",
              trace="at ChargeService.create (charge.service.ts:64)",
              file="tests/idempotencia.spec.ts", line=64),
        _fail("test_conciliacion_diaria_cuadra",
              error_type="ConnectionError",
              message="ETIMEDOUT reaching the settlement provider",
              trace="at SettlementClient.fetch (settlement.client.ts:120)",
              file="tests/conciliacion.spec.ts", line=120),
        _fail("test_notificacion_cobro_al_comercio",
              error_type="ConnectionError",
              message="ECONNREFUSED connecting to the merchant notification service",
              trace="at MerchantNotifier.push (merchant.notifier.ts:74)",
              file="tests/notificaciones.spec.ts", line=74),
    ],
}


# Calendario de runs: 90 días con más densidad en las últimas semanas — un equipo
# que arranca despacio y acelera. El tramo antiguo (>30 días) concentra los fallos:
# son las familias que el equipo etiqueta y con las que el motor se calibra, ANTES
# de que se emitan las actas recientes (por eso las recientes pueden salir "apto").
RUN_CALENDAR: List[RunSpec] = [
    # --- Tramo antiguo (>60 días): el motor aún no sabe nada de este cliente.
    #     Los runs verdes de aquí son el "antes" de los localizadores que luego se rompen.
    RunSpec("banca-movil", "a1c4f20", 88, 37, ("test_transferencia_inmediata_confirma",),
            ("test_login_biometrico_fallback_pin", "test_listado_movimientos_scroll_infinito")),
    RunSpec("api-pagos", "3d9b7e1", 86, 38),
    RunSpec("checkout-suite", "7f2a880", 84, 39, ("test_aplicar_cupon_descuento",),
            ("test_pago_tarjeta_3ds_redirige", "test_boton_finalizar_compra_visible")),
    RunSpec("tienda-online", "b8e0d13", 81, 41, ("test_buscador_devuelve_resultados_relevantes",),
            ("test_ficha_producto_carga_galeria", "test_anadir_al_carrito_actualiza_contador")),
    RunSpec("portal-clientes", "c05e6a4", 79, 36, ("test_descarga_factura_pdf",),
            ("test_actualizar_datos_perfil",)),
    RunSpec("intranet-rrhh", "e4718bc", 76, 33, ("test_solicitud_vacaciones_calcula_dias",),
            ("test_fichaje_entrada_registra_hora", "test_organigrama_muestra_responsable")),
    RunSpec("banca-movil", "9ab3c57", 74, 38, ("test_login_biometrico_fallback_pin",)),
    RunSpec("api-pagos", "1c6f902", 71, 35, ("test_reembolso_parcial_actualiza_importe",)),
    RunSpec("checkout-suite", "d72b45e", 69, 40, ("test_pago_tarjeta_3ds_redirige",)),
    RunSpec("tienda-online", "5e8a1d0", 66, 42, ("test_filtro_categoria_persiste_al_paginar",)),
    RunSpec("portal-clientes", "8b14fa3", 64, 37, ("test_recuperar_contrasena_envia_correo",)),
    RunSpec("intranet-rrhh", "2f9d6b8", 62, 34, ("test_fichaje_entrada_registra_hora",)),
    # El día que se cayó el proveedor de pagos: tres tests fallan a la vez por red.
    # Es lo que el motor reconoce como incidencia de infraestructura y no como defecto.
    RunSpec("api-pagos", "cae1d05", 60, 33,
            ("test_pasarela_responde_bajo_carga", "test_conciliacion_diaria_cuadra",
             "test_notificacion_cobro_al_comercio")),
    # --- Tramo medio (31-60 días): el equipo ya etiqueta y el motor empieza a acertar
    RunSpec("banca-movil", "6c0e83a", 58, 39, ("test_saldo_disponible_tras_operacion",)),
    RunSpec("api-pagos", "f31d7c5", 55, 36, ("test_webhook_reintenta_ante_error_5xx",)),
    RunSpec("checkout-suite", "0a5b2e9", 53, 41,
            ("test_boton_finalizar_compra_visible", "test_stock_reservado_al_pagar")),
    RunSpec("tienda-online", "47cf10d", 50, 43,
            ("test_ficha_producto_carga_galeria", "test_valoraciones_ordenadas_por_fecha")),
    RunSpec("portal-clientes", "aa62b74", 48, 38,
            ("test_actualizar_datos_perfil", "test_cerrar_sesion_invalida_token")),
    RunSpec("intranet-rrhh", "13e9d80", 45, 35,
            ("test_descarga_nomina_mes_actual", "test_aprobacion_gasto_notifica_al_manager")),
    RunSpec("banca-movil", "8d47a12", 43, 40,
            ("test_listado_movimientos_scroll_infinito", "test_alta_beneficiario_valida_iban")),
    RunSpec("api-pagos", "5b0c9f6", 41, 37, ("test_idempotencia_cobro_duplicado",)),
    RunSpec("checkout-suite", "e91f3a7", 38, 42, ("test_email_confirmacion_pedido",)),
    RunSpec("tienda-online", "72a8c05", 36, 44, ("test_anadir_al_carrito_actualiza_contador",)),
    RunSpec("portal-clientes", "c6d02be", 34, 39, ("test_historial_pedidos_pagina_correctamente",)),
    RunSpec("intranet-rrhh", "9e35f81", 32, 36, ("test_organigrama_muestra_responsable",)),
    # --- Tramo reciente (<=30 días): motor calibrado; aquí nacen las actas verdes
    RunSpec("api-pagos", "4f8b6d3", 29, 38),
    RunSpec("banca-movil", "b17e0c9", 27, 41, ("test_alta_beneficiario_valida_iban",)),
    RunSpec("checkout-suite", "3a9d258", 25, 43),
    RunSpec("intranet-rrhh", "d80c4e6", 24, 37, ("test_aprobacion_gasto_notifica_al_manager",)),
    RunSpec("tienda-online", "6b2f7a1", 22, 45, ("test_valoraciones_ordenadas_por_fecha",)),
    RunSpec("portal-clientes", "f47a903", 21, 40, ("test_cerrar_sesion_invalida_token",)),
    RunSpec("checkout-suite", "20e6b8c", 19, 44),
    RunSpec("api-pagos", "8c53f0a", 18, 39, ("test_webhook_reintenta_ante_error_5xx",)),
    RunSpec("banca-movil", "e6109db", 16, 42),
    RunSpec("tienda-online", "5d7b3e2", 15, 46),
    RunSpec("portal-clientes", "91af64d", 13, 41, ("test_descarga_factura_pdf",)),
    RunSpec("intranet-rrhh", "7e2c085", 12, 38),
    RunSpec("checkout-suite", "c4b80f7", 10, 45, ("test_aplicar_cupon_descuento",)),
    RunSpec("api-pagos", "0f6d9a3", 9, 40),
    RunSpec("banca-movil", "a83e5c1", 8, 43),
    RunSpec("tienda-online", "b95028e", 6, 47),
    RunSpec("portal-clientes", "27c1fb6", 5, 42),
    RunSpec("checkout-suite", "6ea4d09", 4, 46, ("test_pago_tarjeta_3ds_redirige",)),
    RunSpec("intranet-rrhh", "d31b7c8", 3, 39),
    RunSpec("api-pagos", "f0a92e5", 2, 41),
    RunSpec("banca-movil", "4c7d6b0", 1, 44),
    RunSpec("checkout-suite", "9b0e37f", 0, 47),
]


# El DOM que tenía cada pantalla cuando el test PASABA. Comparado con el `dom` del
# fallo, es lo que permite al motor distinguir «el localizador se rompió» (alguien
# renombró el selector) de «el test es nuevo y nunca funcionó».
BASELINE_DOM = {
    "test_boton_finalizar_compra_visible":
        '<div class="acciones"><button id="btn-finalizar-compra">Finalizar compra</button></div>',
    "test_anadir_al_carrito_actualiza_contador":
        '<div class="cart"><span class="cart-count">2</span></div>',
    "test_actualizar_datos_perfil":
        '<form id="perfil"><input name="telefono_contacto"/><button>Guardar</button></form>',
    "test_organigrama_muestra_responsable":
        '<div class="org-chart"><div class="org-chart-manager">Ana Ruiz</div></div>',
    "test_pago_tarjeta_3ds_redirige":
        '<div class="pago"><iframe name="3ds-challenge" src="/3ds"></iframe></div>',
    "test_ficha_producto_carga_galeria":
        '<div class="ficha"><img class="gallery-main" src="/p/1.jpg"/></div>',
    "test_login_biometrico_fallback_pin":
        '<div class="acceso"><div data-testid="biometric-prompt">Usa tu huella</div></div>',
    "test_listado_movimientos_scroll_infinito":
        '<ul class="movimientos"><li class="movimiento">Compra</li></ul>',
    "test_fichaje_entrada_registra_hora":
        '<div class="fichaje"><div class="toast-confirmacion">Entrada registrada</div></div>',
}
