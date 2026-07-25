"""Tests indexados de la demo: el material del que vive el grafo de conocimiento.

Los ficheros son los MISMOS en los que ocurren los fallos del catálogo
(`demo_catalog.FAILURE_CATALOG`), para que el grafo y el Defect DNA hablen del
mismo código: al mirar una familia de defectos, el test que la produce existe.

El contenido no es decorativo: se convierte en embedding y es lo que alimenta la
búsqueda de huecos de cobertura, así que cada fichero tiene los nombres de test
reales y las llamadas propias de su dominio.
"""
from typing import Any, Dict, List

# (proyecto, ruta, dominio, [nombres de test que contiene])
_ARCHIVOS = [
    ("checkout-suite", "tests/checkout/cupones.spec.ts", "checkout",
     ["test_aplicar_cupon_descuento", "test_cupon_caducado_no_aplica"]),
    ("checkout-suite", "tests/checkout/pago.spec.ts", "pagos",
     ["test_pago_tarjeta_3ds_redirige", "test_pago_rechazado_muestra_motivo"]),
    ("checkout-suite", "tests/checkout/checkout.spec.ts", "checkout",
     ["test_boton_finalizar_compra_visible", "test_resumen_pedido_coincide"]),
    ("checkout-suite", "tests/checkout/stock.spec.ts", "inventario",
     ["test_stock_reservado_al_pagar", "test_sin_stock_bloquea_compra"]),
    ("checkout-suite", "tests/checkout/notificaciones.spec.ts", "notificaciones",
     ["test_email_confirmacion_pedido"]),
    ("tienda-online", "tests/catalogo/buscador.spec.ts", "busqueda",
     ["test_buscador_devuelve_resultados_relevantes", "test_buscador_tolera_errata"]),
    ("tienda-online", "tests/catalogo/filtros.spec.ts", "catalogo",
     ["test_filtro_categoria_persiste_al_paginar", "test_filtro_precio_acota"]),
    ("tienda-online", "tests/catalogo/ficha.spec.ts", "catalogo",
     ["test_ficha_producto_carga_galeria", "test_ficha_muestra_disponibilidad"]),
    ("tienda-online", "tests/catalogo/carrito.spec.ts", "carrito",
     ["test_anadir_al_carrito_actualiza_contador", "test_vaciar_carrito"]),
    ("tienda-online", "tests/catalogo/valoraciones.spec.ts", "catalogo",
     ["test_valoraciones_ordenadas_por_fecha"]),
    ("banca-movil", "tests/transferencias.spec.ts", "transferencias",
     ["test_transferencia_inmediata_confirma", "test_transferencia_programada"]),
    ("banca-movil", "tests/acceso.spec.ts", "acceso",
     ["test_login_biometrico_fallback_pin", "test_bloqueo_tras_tres_intentos"]),
    ("banca-movil", "tests/cuentas.spec.ts", "cuentas",
     ["test_saldo_disponible_tras_operacion", "test_detalle_cuenta_muestra_iban"]),
    ("banca-movil", "tests/movimientos.spec.ts", "cuentas",
     ["test_listado_movimientos_scroll_infinito", "test_filtro_movimientos_por_fecha"]),
    ("banca-movil", "tests/beneficiarios.spec.ts", "transferencias",
     ["test_alta_beneficiario_valida_iban"]),
    ("portal-clientes", "tests/facturas.spec.ts", "facturacion",
     ["test_descarga_factura_pdf", "test_listado_facturas_ordenado"]),
    ("portal-clientes", "tests/acceso/recuperar.spec.ts", "acceso",
     ["test_recuperar_contrasena_envia_correo"]),
    ("portal-clientes", "tests/portal/perfil.spec.ts", "perfil",
     ["test_actualizar_datos_perfil", "test_cambiar_idioma_persiste"]),
    ("portal-clientes", "tests/pedidos.spec.ts", "pedidos",
     ["test_historial_pedidos_pagina_correctamente"]),
    ("portal-clientes", "tests/acceso/sesion.spec.ts", "acceso",
     ["test_cerrar_sesion_invalida_token", "test_sesion_expira_por_inactividad"]),
    ("intranet-rrhh", "tests/vacaciones.spec.py", "rrhh",
     ["test_solicitud_vacaciones_calcula_dias", "test_solicitud_solapada_se_rechaza"]),
    ("intranet-rrhh", "tests/fichaje.spec.py", "rrhh",
     ["test_fichaje_entrada_registra_hora", "test_fichaje_salida_calcula_jornada"]),
    ("intranet-rrhh", "tests/nominas.spec.py", "nominas",
     ["test_descarga_nomina_mes_actual"]),
    ("intranet-rrhh", "tests/organigrama.spec.py", "rrhh",
     ["test_organigrama_muestra_responsable"]),
    ("intranet-rrhh", "tests/gastos.spec.py", "gastos",
     ["test_aprobacion_gasto_notifica_al_manager", "test_gasto_sin_justificante_se_rechaza"]),
    ("api-pagos", "tests/pasarela.spec.ts", "pagos",
     ["test_pasarela_responde_bajo_carga", "test_pasarela_devuelve_codigo_autorizacion"]),
    ("api-pagos", "tests/reembolsos.spec.ts", "pagos",
     ["test_reembolso_parcial_actualiza_importe", "test_reembolso_total_cierra_cobro"]),
    ("api-pagos", "tests/webhooks.spec.ts", "integraciones",
     ["test_webhook_reintenta_ante_error_5xx", "test_webhook_firma_payload"]),
    ("api-pagos", "tests/idempotencia.spec.ts", "pagos",
     ["test_idempotencia_cobro_duplicado"]),
    ("api-pagos", "tests/conciliacion.spec.ts", "conciliacion",
     ["test_conciliacion_diaria_cuadra"]),
    ("api-pagos", "tests/notificaciones.spec.ts", "integraciones",
     ["test_notificacion_cobro_al_comercio"]),
]


def _cuerpo_playwright(proyecto: str, dominio: str, tests: List[str]) -> str:
    casos = "\n\n".join(
        f"""  test('{t.replace('test_', '').replace('_', ' ')}', async ({{ page }}) => {{
    await page.goto('/{dominio}');
    await page.getByTestId('{dominio}-root').waitFor();
    // Espera explícita al estado, nunca un sleep fijo (convención del equipo)
    await expect(page.getByTestId('{dominio}-listo')).toBeVisible();
  }});"""
        for t in tests)
    return (f"""import {{ test, expect }} from '@playwright/test';

// Suite de {dominio} — proyecto {proyecto}
test.describe('{dominio}', () => {{
{casos}
}});
""")


def _cuerpo_pytest(proyecto: str, dominio: str, tests: List[str]) -> str:
    casos = "\n\n".join(
        f"""def {t}(page):
    \"\"\"{t.replace('test_', '').replace('_', ' ').capitalize()}.\"\"\"
    page.goto("/{dominio}")
    page.get_by_test_id("{dominio}-root").wait_for()
    assert page.get_by_test_id("{dominio}-listo").is_visible()"""
        for t in tests)
    return (f'''import pytest

# Suite de {dominio} — proyecto {proyecto}


{casos}
''')


def _asset(proyecto: str, ruta: str, dominio: str, tests: List[str]) -> Dict[str, Any]:
    es_python = ruta.endswith(".py")
    return {
        "path": ruta,
        "framework": "pytest" if es_python else "playwright",
        "domain": dominio,
        "content": (_cuerpo_pytest if es_python else _cuerpo_playwright)(proyecto, dominio, tests),
    }


ASSETS_POR_PROYECTO: List[Dict[str, Any]] = [
    _asset(proyecto, ruta, dominio, tests) for proyecto, ruta, dominio, tests in _ARCHIVOS
]
