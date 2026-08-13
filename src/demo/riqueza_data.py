"""Riqueza de Demo MTP: la org de una consultora con seis proyectos vivos y
desigualmente cuidados. Solo datos; la siembra vive en seed_riqueza.py.

Los proyectos del arco (checkout-suite=95, banca-movil=25) están PROTEGIDOS:
solo runs verdes y cero conocimiento nuevo — los tests lo imponen.
"""

PROTECTED = ("checkout-suite", "banca-movil")

# Perfil semanal por proyecto. fail_weeks: cada cuántas semanas ISO el run lleva
# fallos (0 = nunca); los fallos reutilizan firmas EXISTENTES del proyecto (BD).
# n_pass varía con la semana (determinista) para que los manifiestos no sean clones.
WEEKLY_PROFILE = {
    "checkout-suite":  {"n_pass": 42, "fail_weeks": 0},
    "banca-movil":     {"n_pass": 28, "fail_weeks": 0},
    "tienda-online":   {"n_pass": 35, "fail_weeks": 2},   # semanas pares: 1-2 fallos
    "portal-clientes": {"n_pass": 31, "fail_weeks": 3},   # cada 3 semanas: 1 fallo
    "api-pagos":       {"n_pass": 24, "fail_weeks": 0},
    "intranet-rrhh":   {"n_pass": 18, "fail_weeks": 0},
}

# Triaje de las familias 'unknown' (matching por keywords sobre título+tests+mensaje,
# el mecanismo _find_family de seed_knowledge). Once entradas para dejar exactamente
# DOS familias sin triar (pago_tarjeta y transferencia_sepa) — una bandeja totalmente
# vacía parece maqueta. Las entradas cuyo objetivo ya esté etiquetado no hacen nada
# (el matching corre solo sobre unknown): son inofensivas por construcción.
FAMILY_TRIAGE = [
    (("idempotencia_cobros",), "real",
     "Cargo duplicado reproducible con la misma Idempotency-Key; el PSP confirma que"
     " el retry no es idempotente. Ticket abierto a pagos."),
    (("webhook_confirmacion",), "infra",
     "ENOTFOUND del hostname del webhook: DNS interno de staging, no el código."
     " Correlaciona con las ventanas de mantenimiento de Plataforma."),
    (("reembolso_total",), "infra",
     "ECONNREFUSED al sandbox del PSP fuera de su horario; el reembolso real funciona."
     " Espaciar la suite o mockear fuera de horario."),
    (("descarga_facturas", "exportar_csv"), "infra",
     "El servicio de facturas de staging se apaga a las 20:00; los dos tests fallan"
     " solo en la nocturna tardía."),
    (("dos_factor",), "real",
     "El segundo factor no se exige tras el rediseño del login: regresión de seguridad"
     " confirmada a mano. Prioridad alta."),
    (("alta_domiciliacion",), "flaky",
     "ECONNRESET intermitente en la firma OTP; no reproduce en local ni correlaciona"
     " con despliegues. En observación con retry."),
    (("cupon_descuento",), "real",
     "El cupón se aplica dos veces al reintentar el pago; caja lo confirmó en el"
     " arqueo. Bug de negocio, no del test."),
    (("nomina_pdf",), "maintenance",
     "El formato del importe cambió con la librería de PDF (coma decimal); el test"
     " esperaba el formato viejo. Actualizar el fixture."),
    (("confirmacion_pedido",), "real",
     "El pedido queda en 'pendiente' con el pago cobrado: el consumidor del webhook"
     " va atrasado. Ver la lección del webhook — se escala a Plataforma, no a Pagos."),
    (("historico_movimientos",), "infra",
     "ECONNRESET al consultar movimientos solo en la franja del backup de la BD de"
     " staging (02:00-02:30). Reprogramar la suite o excluir la franja."),
    (("autorizacion_psp",), "infra",
     "Socket hang up del sandbox del PSP en frío: la primera petición tras el reposo"
     " siempre cae. Un warm-up antes de la suite lo elimina."),
]

# Conocimiento por proyecto — desigual A PROPÓSITO (la distribución hace creíbles
# los índices). family_keywords vincula lecciones a familias (memoria_defectos).
KB_ITEMS = [
    # ----------------------------------------------------- tienda-online (~75)
    {"kind": "runbook", "project": "tienda-online", "domain": "checkout",
     "title": "Levantar tienda-online con el catálogo de staging",
     "challenge": "Sin el catálogo sincronizado, la mitad de la suite falla por SKUs inexistentes y se pierde la mañana triando falsos rojos.",
     "approach": "docker compose up (perfil tienda) → `make catalogo-sync` (trae el snapshot nocturno de staging) → smoke: `test_confirmacion_pedido` con el SKU de referencia debe pasar antes de lanzar nada más.",
     "outcome": "Entorno útil en 10 minutos; los falsos rojos por catálogo desaparecieron.",
     "tags": ["entorno", "catalogo"]},
    {"kind": "dato_prueba", "project": "tienda-online", "domain": "checkout",
     "title": "Cupones de prueba y sus reglas",
     "challenge": "Cada cupón de prueba activa una rama distinta del descuento; usar el equivocado esconde el bug de doble aplicación.",
     "approach": "DEMO15 → 15 % una vez por pedido (el caso del bug histórico). ENVIOGRATIS → solo elimina portes. CADUCADO01 → siempre rechazado (para el mensaje de error). Se reponen con la ventana nocturna.",
     "tags": ["cupones", "datos"]},
    {"kind": "contacto", "project": "tienda-online", "domain": "logistica",
     "title": "Las devoluciones las lleva el equipo de Logística",
     "challenge": "Los abonos de las devoluciones de prueba se quedaban colgados y nadie sabía a quién escalar.",
     "approach": "Canal #logistica-soporte. Pedirles: desbloquear abonos de prueba atascados y reponer el stock del SKU de devoluciones. NO pedirles: nada del cobro — eso es de Pagos.",
     "tags": ["equipo", "devoluciones"]},
    {"kind": "leccion", "project": "tienda-online", "domain": "pagos",
     "title": "El doble descuento del cupón aparece solo al reintentar el pago",
     "family_keywords": ("cupon_descuento",),
     "challenge": "El descuento duplicado no reproduce en el flujo feliz: solo cuando el primer intento de pago falla y se reintenta.",
     "approach": "Reproducir SIEMPRE con la tarjeta de prueba rechazada primero y la aprobada después; el cupón se re-aplica en el segundo intento. La validación debe mirar el pedido, no la sesión.",
     "outcome": "El triaje de este patrón pasó de tarde entera a veinte minutos.",
     "tags": ["cupones", "retry"]},
    {"kind": "leccion", "project": "tienda-online", "domain": "pedidos",
     "title": "Un pedido 'pendiente' tras pagar es el webhook, no el pago",
     "family_keywords": ("confirmacion_pedido",),
     "challenge": "Pedidos pagados que se quedan en 'pendiente' hacían sospechar del PSP y se escalaban mal.",
     "approach": "Mirar primero la cola del webhook de confirmación: si el evento está encolado, el pago fue bien y es el consumidor el que va atrasado. Escalar a Plataforma, no a Pagos.",
     "tags": ["webhook", "triaje"]},
    {"kind": "regla_negocio", "project": "tienda-online", "domain": "pagos",
     "title": "Un cupón se aplica una sola vez por pedido",
     "challenge": "El arqueo de caja detectó descuentos duplicados en pedidos reintentados.",
     "approach": "La regla vive en el pedido, no en la sesión de pago: reintentar el cobro nunca re-aplica el descuento. Todo test de retry debe verificar el importe final del pedido.",
     "tags": ["cupones", "negocio"]},
    {"kind": "patron", "project": "tienda-online", "domain": "pedidos",
     "title": "Esperar el estado del pedido por polling con tope, nunca sleep fijo",
     "challenge": "Los sleep fijos hacían la suite lenta en local y flaky en CI (el webhook tarda distinto en cada entorno).",
     "approach": "Polling del estado con tope de 30 s y salida temprana; el tope se declara en el helper `esperarEstadoPedido`, no en cada test.",
     "tags": ["flaky", "patron"]},
    # --------------------------------------------------- portal-clientes (~65)
    {"kind": "runbook", "project": "portal-clientes", "domain": "facturacion",
     "title": "Reponer las facturas de prueba antes de la nocturna",
     "challenge": "La suite de facturación agota las facturas descargables y la nocturna del día siguiente falla en cadena.",
     "approach": "`make facturas-reset` contra staging ANTES de las 20:00 (a esa hora se apaga el servicio de facturas). Si se pasó la hora, pedir reposición manual en #plataforma.",
     "outcome": "La nocturna de facturación dejó de fallar los lunes.",
     "tags": ["facturas", "nocturna"]},
    {"kind": "decision", "project": "portal-clientes", "domain": "auth",
     "title": "El OTP real solo se prueba en la ventana acordada con el emisor",
     "challenge": "Probar la firma OTP real fuera de la ventana acordada saturaba el sandbox del emisor y provocaba bloqueos de cuenta.",
     "approach": "OTP real: solo martes 10:00-12:00 (acordado con el emisor en julio de 2026). El resto de la semana, el simulador. El test nocturno usa siempre el simulador.",
     "outcome": "Cero bloqueos de cuenta desde el acuerdo.",
     "tags": ["otp", "alcance"]},
    {"kind": "leccion", "project": "portal-clientes", "domain": "facturacion",
     "title": "Los ECONNREFUSED de facturas son el apagado de staging a las 20:00",
     "family_keywords": ("descarga_facturas",),
     "challenge": "Los rechazos de conexión del servicio de facturas parecían caídas y disparaban falsas alarmas.",
     "approach": "Mirar la hora del fallo antes que el log: después de las 20:00 es el apagado programado de staging. Reordenar la suite para que facturación corra antes, o marcar la franja en el reporte.",
     "tags": ["staging", "triaje"]},
    # -------------------------------------------------------- api-pagos (~55)
    {"kind": "leccion", "project": "api-pagos", "domain": "pagos",
     "title": "La idempotencia se verifica con la MISMA key, no con una nueva por retry",
     "family_keywords": ("idempotencia_cobros",),
     "challenge": "El test generaba una Idempotency-Key nueva en cada retry y el doble cargo pasaba inadvertido.",
     "approach": "El retry del test reutiliza la key del intento original — como hace el cliente real. La aserción cuenta cargos por key, no por respuesta.",
     "outcome": "El doble cargo se detecta en PR desde el cambio.",
     "tags": ["idempotencia", "retry"]},
    {"kind": "patron", "project": "api-pagos", "domain": "pagos",
     "title": "Todo test de cobro limpia sus cargos en el teardown, pase o falle",
     "challenge": "Los cargos residuales de tests fallidos contaminaban las aserciones de los siguientes y producían rojos en cascada.",
     "approach": "El teardown anula por Idempotency-Key todo cargo creado por el test, dentro de un finally. Un helper común (`limpiarCargos`) para no repetirlo.",
     "tags": ["teardown", "patron"]},
    {"kind": "regla_negocio", "project": "api-pagos", "domain": "pagos",
     "title": "Un reembolso nunca supera el importe capturado",
     "challenge": "Un redondeo permitía reembolsar céntimos de más en importes con tres decimales.",
     "approach": "El reembolso se valida contra el importe capturado en la MISMA divisa y precisión; los tests cubren los tres redondeos (arriba, abajo, banca).",
     "tags": ["reembolsos", "negocio"]},
    # ----------------------------------------------------- intranet-rrhh (~35)
    {"kind": "glosario", "project": "intranet-rrhh", "domain": "nominas",
     "title": "Neto, bruto y devengo en las nóminas de prueba",
     "challenge": None,
     "approach": "Bruto: antes de retenciones. Neto: lo que se transfiere. Devengo: el periodo trabajado que la nómina paga — el PDF de prueba muestra los tres y los tests los confunden a menudo.",
     "tags": ["glosario", "nominas"]},
]

# Specs indexados como test assets (plan de pruebas + huecos regla_sin_test).
_SPEC_TIENDA_CHECKOUT = """import { test, expect } from '@playwright/test';
import { esperarEstadoPedido, limpiarCarrito } from './helpers';

test.describe('checkout de tienda-online', () => {
  test.afterEach(limpiarCarrito);

  test('un pedido pagado se confirma', async ({ page }) => {
    await page.goto('/producto/sku-referencia');
    await page.click('#comprar');
    await page.fill('#tarjeta', '4111 1111 1111 1111');
    await page.click('#pagar');
    await esperarEstadoPedido(page, 'confirmado', { timeoutMs: 30_000 });
  });

  test('el stock reservado expira a los 15 minutos', async ({ page }) => {
    await page.goto('/producto/sku-ultima-unidad');
    await page.click('#comprar');
    await expect(page.locator('#reserva-ttl')).toContainText('15');
  });
});
"""

_SPEC_TIENDA_CUPONES = """import { test, expect } from '@playwright/test';

test('un cupon se aplica una sola vez aunque el pago se reintente', async ({ page }) => {
  await page.goto('/checkout?cupon=DEMO15');
  await page.fill('#tarjeta', '4000 0000 0000 0002'); // rechazada: fuerza el retry
  await page.click('#pagar');
  await page.fill('#tarjeta', '4111 1111 1111 1111');
  await page.click('#pagar');
  const total = await page.locator('#total').innerText();
  expect(total).toBe('85,00 EUR'); // 15 % UNA vez sobre 100
});
"""

_SPEC_TIENDA_DEVOLUCIONES = """import { test, expect } from '@playwright/test';

test('una devolucion emite el abono en plazo', async ({ request }) => {
  const r = await request.post('/api/devoluciones', { data: { pedido: 'PED-DEMO-1' } });
  expect(r.ok()).toBeTruthy();
  const abono = await request.get('/api/abonos?pedido=PED-DEMO-1');
  expect((await abono.json()).estado).toBe('emitido');
});
"""

_SPEC_PORTAL_FACTURAS = """import { test, expect } from '@playwright/test';

// OJO: staging apaga el servicio de facturas a las 20:00 — esta suite corre ANTES.
test('descargar la ultima factura', async ({ page }) => {
  await page.goto('/facturas');
  const descarga = page.waitForEvent('download');
  await page.click('#descargar-ultima');
  expect((await descarga).suggestedFilename()).toMatch(/factura-.*\\.pdf/);
});
"""

_SPEC_PORTAL_OTP = """import { test, expect } from '@playwright/test';

// El OTP real solo en la ventana acordada (martes 10-12); aqui, el simulador.
test('el segundo factor es obligatorio', async ({ page }) => {
  await page.goto('/login');
  await page.fill('#usuario', 'comprador-completo');
  await page.fill('#password', 'password-de-prueba');
  await page.click('#entrar');
  await expect(page.locator('#otp')).toBeVisible(); // sin OTP no hay sesion
});
"""

_SPEC_API_IDEMPOTENCIA = """import test from 'node:test';
import assert from 'node:assert';

test('la misma Idempotency-Key nunca produce dos cargos', async () => {
  const key = 'idem-demo-001';
  await cobrar({ importe: 1000, key });
  await cobrar({ importe: 1000, key }); // retry del cliente real: MISMA key
  const cargos = await cargosPorKey(key);
  assert.equal(cargos.length, 1);
});
"""

_SPEC_API_REEMBOLSOS = """import test from 'node:test';
import assert from 'node:assert';

test('un reembolso no supera el importe capturado', async () => {
  const cargo = await cobrar({ importe: 1999, key: 'idem-demo-002' });
  const r = await reembolsar({ cargo: cargo.id, importe: 2000 });
  assert.equal(r.estado, 'rechazado'); // ni un centimo de mas
});
"""

_SPEC_RRHH_NOMINAS = """import { test, expect } from '@playwright/test';

test('el PDF de nomina muestra el neto con coma decimal', async ({ page }) => {
  await page.goto('/nominas/ultima');
  await expect(page.locator('#neto')).toHaveText(/\\d{1,3}(\\.\\d{3})*,\\d{2} EUR/);
});
"""

_SPEC_BANCA_TRANSFERENCIAS = """import { test, expect } from '@playwright/test';

test('una transferencia requiere confirmacion explicita', async ({ page }) => {
  await page.goto('/transferencias/nueva');
  await page.fill('#importe', '100');
  await page.click('#enviar');
  await expect(page.locator('#confirmar')).toBeVisible(); // nunca en un solo paso
});
"""

_SPEC_BANCA_LOGIN2FA = """import { test, expect } from '@playwright/test';

test('el login de banca exige segundo factor siempre', async ({ page }) => {
  await page.goto('/login');
  await page.fill('#usuario', 'usuario-prueba');
  await page.fill('#password', 'password-de-prueba');
  await page.click('#entrar');
  await expect(page.locator('#segundo-factor')).toBeVisible();
});
"""

ASSETS = [
    {"path": "tests/tienda/checkout.spec.ts", "framework": "playwright",
     "domain": "checkout", "content": _SPEC_TIENDA_CHECKOUT},
    {"path": "tests/tienda/cupones.spec.ts", "framework": "playwright",
     "domain": "pagos", "content": _SPEC_TIENDA_CUPONES},
    {"path": "tests/tienda/devoluciones.spec.ts", "framework": "playwright",
     "domain": "logistica", "content": _SPEC_TIENDA_DEVOLUCIONES},
    {"path": "tests/portal/facturas.spec.ts", "framework": "playwright",
     "domain": "facturacion", "content": _SPEC_PORTAL_FACTURAS},
    {"path": "tests/portal/otp.spec.ts", "framework": "playwright",
     "domain": "auth", "content": _SPEC_PORTAL_OTP},
    {"path": "tests/api-pagos/idempotencia.test.ts", "framework": "junit",
     "domain": "pagos", "content": _SPEC_API_IDEMPOTENCIA},
    {"path": "tests/api-pagos/reembolsos.test.ts", "framework": "junit",
     "domain": "pagos", "content": _SPEC_API_REEMBOLSOS},
    {"path": "tests/rrhh/nominas.spec.ts", "framework": "playwright",
     "domain": "nominas", "content": _SPEC_RRHH_NOMINAS},
    {"path": "tests/banca/transferencias.spec.ts", "framework": "playwright",
     "domain": "pagos", "content": _SPEC_BANCA_TRANSFERENCIAS},
    {"path": "tests/banca/login2fa.spec.ts", "framework": "playwright",
     "domain": "auth", "content": _SPEC_BANCA_LOGIN2FA},
]
