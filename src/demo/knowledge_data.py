"""Corpus de conocimiento de la demo (datos puros, sin lógica).

Mundo de la demo: e-commerce "checkout-suite" (checkout, pagos, perfil,
autenticación, informes) — coherente con los fixtures de runs. Org B vive en
otro dominio (banca) para que el aislamiento multi-tenant se vea con contenido,
no con una pantalla vacía.

`family_keywords`: palabras del título de una familia de defectos sembrada; el
seed las usa para enlazar el item a la familia real (alimenta el grafo).
"""

PROJECT = "checkout-suite"

KNOWLEDGE_ORG_A = [
    # ------------------------------------------------------------- reglas de negocio
    {
        "kind": "regla_negocio",
        "title": "Un pedido no puede confirmarse sin autorización del PSP",
        "challenge": "Pedidos confirmados con pagos rechazados generaban anulaciones manuales y reclamaciones.",
        "approach": "La confirmación exige callback de autorización del PSP; sin él, el pedido queda en 'pendiente de pago' y caduca a los 30 minutos.",
        "outcome": "Cero pedidos confirmados sin cobro desde el cambio.",
        "domain": "pagos",
        "tags": ["checkout", "pagos", "negocio"],
    },
    {
        "kind": "regla_negocio",
        "title": "El stock se reserva 15 minutos al iniciar el checkout",
        "challenge": "Dos compradores podían pagar la última unidad a la vez.",
        "approach": "Reserva blanda al entrar en checkout con TTL de 15 min; los tests de concurrencia deben esperar la expiración o liberar la reserva en el teardown.",
        "domain": "checkout",
        "tags": ["checkout", "stock", "concurrencia"],
    },
    {
        "kind": "regla_negocio",
        "title": "Los precios se muestran con IVA según el país de la sesión",
        "challenge": "Los tests con datos de precio fijos fallaban al cambiar el país por defecto del entorno.",
        "approach": "Los asserts de precio usan el precio base × tipo de IVA del país de la sesión, nunca literales.",
        "domain": "catalogo",
        "tags": ["precios", "iva", "internacionalizacion"],
    },
    # ------------------------------------------------------------------------ flujos
    {
        "kind": "flujo",
        "title": "Checkout completo: invitado y usuario registrado",
        "challenge": "Cubrir las dos variantes sin duplicar el suite entero.",
        "approach": "Carrito → identificación (invitado o login) → dirección → envío → pago (sandbox PSP) → confirmación. La variante se inyecta como fixture parametrizada; los pasos posteriores a identificación son comunes.",
        "domain": "checkout",
        "tags": ["checkout", "e2e", "flujo-critico"],
    },
    {
        "kind": "flujo",
        "title": "Alta y edición de perfil de usuario",
        "challenge": "El rediseño de la página de perfil cambió selectores y validaciones.",
        "approach": "Registro → verificación de email (interceptada en sandbox) → edición de datos → guardado. Selectores por data-testid tras el rediseño; el guardado dispara un PATCH y un toast de confirmación.",
        "domain": "perfil",
        "tags": ["perfil", "e2e"],
        "family_keywords": ("test_perfil",),
    },
    {
        "kind": "flujo",
        "title": "Exportación de informes CSV desde el panel de administración",
        "challenge": "La exportación es asíncrona: el fichero llega por polling, no en la respuesta.",
        "approach": "Solicitar export → esperar job 'completed' (máx 60 s) → descargar → validar cabeceras y nº de filas contra la API.",
        "domain": "informes",
        "tags": ["informes", "csv", "async"],
        "family_keywords": ("test_export",),
    },
    # ----------------------------------------------------------------------- riesgos
    {
        "kind": "riesgo",
        "title": "La pasarela de pagos sandbox limita a 30 peticiones/minuto",
        "challenge": "Suites paralelas agotan la cuota y los pagos fallan con 429 — parecen bugs de checkout.",
        "approach": "Serializar los tests que tocan el PSP real de sandbox y stubear el resto; etiquetar los 429 como infra, no como fallo de producto.",
        "domain": "pagos",
        "tags": ["pagos", "sandbox", "rate-limit", "infra"],
    },
    {
        "kind": "riesgo",
        "title": "Staging comparte base de datos entre las suites nocturnas",
        "challenge": "Datos residuales de una suite contaminan la siguiente (usuarios duplicados, stock en negativo).",
        "approach": "Prefijos únicos por ejecución en datos creados + limpieza por prefijo en el teardown global.",
        "domain": "infra-ci",
        "tags": ["staging", "datos-de-prueba", "aislamiento"],
    },
    {
        "kind": "riesgo",
        "title": "Frontend cambia IDs del DOM sin aviso al equipo de QA",
        "challenge": "Cada rediseño rompe selectores y quema horas de triaje en falsos 'bugs'.",
        "approach": "Acuerdo de data-testid estables como contrato; Mnemo triaja estos casos como mantenimiento y propone el parche de selector.",
        "domain": "perfil",
        "tags": ["mantenimiento", "selectores", "contrato-frontend"],
        "family_keywords": ("test_login", "test_perfil"),
    },
    # ---------------------------------------------------------------------- glosario
    {
        "kind": "glosario",
        "title": "PSP (Payment Service Provider)",
        "challenge": "Término recurrente en incidencias de pago que confunde a los QA nuevos.",
        "approach": "Proveedor externo que autoriza y captura los pagos (en sandbox: simulador con tarjetas de prueba). Sus estados: authorized, captured, declined, expired.",
        "domain": "pagos",
        "tags": ["glosario", "pagos"],
    },
    {
        "kind": "glosario",
        "title": "Test flaky",
        "challenge": "Se usaba como cajón de sastre para cualquier fallo no entendido.",
        "approach": "Test que alterna pasa/falla sin cambio de código. Criterio operativo: falla y pasa en el mismo commit (retry o reejecución). Si solo falla, NO es flaky: es un bug o mantenimiento.",
        "domain": "infra-ci",
        "tags": ["glosario", "flaky", "triaje"],
        "family_keywords": ("test_checkout",),
    },
    {
        "kind": "glosario",
        "title": "Acta de aseguramiento (certificado firmado)",
        "challenge": "«¿Está listo el release?» se respondía con opiniones.",
        "approach": "Documento JSON canónico con el veredicto del run (apto / apto-con-reservas / no-apto), evidencia y firma Ed25519 verificable por terceros sin cuenta en la plataforma.",
        "domain": "proceso",
        "tags": ["glosario", "acta", "release"],
    },
    # ---------------------------------------------------------------------- lecciones
    {
        "kind": "leccion",
        "title": "El selector #guardar pasó a #guardar-cambios en el rediseño de perfil",
        "challenge": "test_perfil rompió tras el deploy del rediseño; el error ('locator not found') parecía un bug de guardado.",
        "approach": "Comparar el DOM del fallo con la última baseline verde: el botón existe con id nuevo. Actualizar el selector y pedir data-testid estable.",
        "outcome": "Patrón detectable automáticamente: fallo de mantenimiento, no de producto.",
        "domain": "perfil",
        "tags": ["leccion", "selectores", "mantenimiento"],
        "family_keywords": ("test_perfil",),
        "source": "triaje",
    },
    {
        "kind": "leccion",
        "title": "test_checkout_flujo es intermitente por la carga del widget del PSP",
        "challenge": "Fallaba ~1 de cada 4 ejecuciones en el paso de pago, siempre en runners lentos.",
        "approach": "El iframe del PSP tarda hasta 8 s en runners fríos; la espera fija de 5 s no llega. Esperar al evento de 'widget ready' en vez de un sleep.",
        "outcome": "Reclasificado como flaky de infraestructura; estable tras la espera explícita.",
        "domain": "pagos",
        "tags": ["leccion", "flaky", "esperas"],
        "family_keywords": ("test_checkout",),
        "source": "triaje",
    },
    {
        "kind": "leccion",
        "title": "La exportación CSV rompe con caracteres no UTF-8 en nombres de producto",
        "challenge": "test_export_csv falla solo cuando el catálogo de staging contiene productos importados con encoding legacy.",
        "approach": "Es un bug real del serializador (no escapa Latin-1). Reproducible con el producto 'Café São Paulo'. Ticket abierto al equipo de catálogo.",
        "outcome": "Fallo real confirmado — el gate debe bloquear hasta el fix.",
        "domain": "informes",
        "tags": ["leccion", "bug-real", "encoding"],
        "family_keywords": ("test_export",),
        "source": "triaje",
    },
    {
        "kind": "leccion",
        "title": "El login rompió por el selector #submit renombrado",
        "challenge": "test_login pasó de verde a rojo entre dos deploys sin cambios en la suite ('locator not found: #submit').",
        "approach": "El botón de entrar cambió de id en el rediseño del formulario. Mismo patrón que el perfil: comparar DOM rojo contra baseline verde y actualizar el selector.",
        "outcome": "Triado como mantenimiento; segundo caso del mismo patrón → elevado a riesgo de contrato con frontend.",
        "domain": "autenticacion",
        "tags": ["leccion", "selectores", "mantenimiento"],
        "family_keywords": ("test_login",),
        "source": "triaje",
    },
    # -------------------------------------------------------------------------- retos
    {
        "kind": "reto",
        "title": "Las tarjetas de prueba del sandbox caducan cada trimestre",
        "challenge": "Cada cambio de trimestre, media suite de pagos falla por tarjetas expiradas y nadie recuerda renovarlas.",
        "approach": "Pendiente: generar el juego de tarjetas en el setup del suite desde la API del PSP en vez de mantener una lista estática.",
        "domain": "pagos",
        "tags": ["reto", "datos-de-prueba", "sandbox"],
        "confidence": "inferido",
    },
    {
        "kind": "reto",
        "title": "El onboarding de un QA nuevo tarda ~3 semanas por conocimiento tribal",
        "challenge": "Reglas de negocio, trampas del entorno y jerga viven en cabezas y chats; cada incorporación repite las mismas preguntas.",
        "approach": "Capturar lecciones y reglas en la memoria del equipo y generar la ruta de aprendizaje por dominio desde ahí.",
        "domain": "proceso",
        "tags": ["reto", "onboarding", "conocimiento"],
        "confidence": "inferido",
    },
    # ----------------------------------------------------------------------- patrones
    {
        "kind": "patron",
        "title": "Esperas explícitas por estado, nunca sleeps fijos",
        "challenge": "Los sleeps calibrados para el runner rápido fallan en el lento y ralentizan al rápido.",
        "approach": "Esperar condiciones observables (evento, request completada, elemento interactivo). Presupuesto de espera centralizado en config, no disperso en cada test.",
        "domain": "infra-ci",
        "tags": ["patron", "esperas", "estabilidad"],
    },
    {
        "kind": "patron",
        "title": "Page Object de checkout con selectores data-testid",
        "challenge": "Selectores CSS frágiles duplicados por todo el suite.",
        "approach": "Un Page Object por paso del checkout; solo data-testid pactados con frontend. Un cambio de UI = un archivo que tocar.",
        "domain": "checkout",
        "tags": ["patron", "page-object", "selectores"],
    },
    {
        "kind": "patron",
        "title": "Reintento único + cuarentena para flaky confirmados",
        "challenge": "Reintentos ilimitados escondían bugs reales; sin reintentos, el ruido flaky tapaba el dashboard.",
        "approach": "Un único retry automático; si pasa al segundo intento se marca flaky y la familia entra en cuarentena visible con dueño y fecha — nunca se desactiva en silencio.",
        "domain": "infra-ci",
        "tags": ["patron", "flaky", "cuarentena"],
    },
]

KNOWLEDGE_ORG_B = [
    {
        "kind": "regla_negocio",
        "title": "Una transferencia > 10.000 € exige doble aprobación",
        "challenge": "Los tests de transferencias altas fallaban esperando confirmación inmediata.",
        "approach": "El flujo de importe alto queda 'pendiente de segundo aprobador'; el test debe aprobar con un segundo usuario de prueba con rol supervisor.",
        "domain": "transferencias",
        "tags": ["negocio", "aprobaciones"],
        "project": "banca-online",
    },
    {
        "kind": "leccion",
        "title": "El OTP del sandbox expira en 30 segundos",
        "challenge": "Fallos intermitentes de login en runners con el reloj desincronizado.",
        "approach": "Sincronizar NTP en los runners y pedir el OTP justo antes de usarlo, no en el setup del suite.",
        "domain": "autenticacion",
        "tags": ["leccion", "otp", "flaky"],
        "project": "banca-online",
        "source": "triaje",
    },
    {
        "kind": "glosario",
        "title": "SCA (Strong Customer Authentication)",
        "challenge": "Requisito PSD2 que aparece en la mitad de las incidencias de pagos.",
        "approach": "Autenticación reforzada del cliente (dos factores) exigida por PSD2 para operaciones de pago; en sandbox se simula con el OTP fijo del entorno.",
        "domain": "autenticacion",
        "tags": ["glosario", "psd2"],
        "project": "banca-online",
    },
]

# Causas raíz por familia. Keywords = nombre del test (inequívoco: los títulos de
# familia son el error_type y los mensajes comparten palabras como "locator").
# La de test_perfil solo aplica si ya hubo un push en vivo (Acto 1) que creó la familia.
ROOT_CAUSES = [
    (
        ("test_login",),
        "El rediseño del formulario de acceso renombró el botón de entrar (#submit) sin "
        "data-testid estable; el test localiza por id y rompe. No es un defecto de producto: "
        "es mantenimiento de selector. Acción: parche de selector + acuerdo de data-testid "
        "con frontend.",
    ),
    (
        ("test_checkout",),
        "El iframe del widget del PSP tarda hasta 8 s en runners fríos; la espera fija de 5 s "
        "produce fallos intermitentes (~25%). Causa de infraestructura de test, no de producto. "
        "Acción: espera explícita al evento 'widget ready'.",
    ),
    (
        ("test_export",),
        "El serializador CSV no escapa caracteres fuera de UTF-8 (catálogo legacy en Latin-1). "
        "Reproducible con 'Café São Paulo'. Defecto real del backend de informes; bloqueado "
        "hasta el fix del equipo de catálogo.",
    ),
    (
        ("test_perfil",),
        "El rediseño de la página de perfil renombró el botón de guardado de #guardar a "
        "#guardar-cambios sin data-testid estable. Mismo patrón que el login: mantenimiento "
        "de selector, no defecto de producto. Acción: parche de selector propuesto por self-heal.",
    ),
]

# Etiquetas humanas para la calibración (keywords por nombre de test, label, razón).
# checkout lleva una DISCREPANCIA deliberada (motor: flaky → humano: infra) para que la
# accuracy del foso sea realista (<100%) y se pueda narrar la corrección en la demo.
FAMILY_LABELS = [
    (("test_login",), "maintenance", "Selector #submit renombrado en el rediseño; confirmado con el diff de DOM."),
    (("test_checkout",), "infra", "Los timeouts correlan con runners fríos y latencia del sandbox del PSP, no con el test."),
    (("test_export",), "real", "Bug de encoding reproducible; ticket abierto a catálogo."),
    (("test_perfil",), "maintenance", "Selector #guardar→#guardar-cambios; confirmado con el diff de DOM del push."),
]

from src.demo.demo_test_assets import ASSETS_POR_PROYECTO  # noqa: E402

_TEST_ASSETS_CURADOS = [
    {
        "path": "tests/checkout.spec.ts",
        "framework": "playwright",
        "domain": "checkout",
        "content": """import { test, expect } from '@playwright/test';
import { CheckoutPage } from './pages/checkout.page';

test.describe('checkout - flujo completo', () => {
  test('invitado completa compra con tarjeta de prueba', async ({ page }) => {
    const checkout = new CheckoutPage(page);
    await checkout.addToCart('SKU-1042');
    await checkout.startAsGuest('qa+guest@example.com');
    await checkout.fillShipping({ ciudad: 'Madrid', cp: '28001' });
    // Espera explícita al widget del PSP (nunca sleep fijo — ver patrón del equipo)
    await checkout.waitForPaymentWidgetReady();
    await checkout.payWithTestCard('4111 1111 1111 1111');
    await expect(page.getByTestId('order-confirmation')).toBeVisible();
    await expect(page.getByTestId('order-number')).toHaveText(/PED-\\d{6}/);
  });
});
""",
    },
    {
        "path": "tests/perfil.spec.ts",
        "framework": "playwright",
        "domain": "perfil",
        "content": """import { test, expect } from '@playwright/test';

test.describe('perfil de usuario', () => {
  test('edita y guarda los datos del perfil', async ({ page }) => {
    await page.goto('/perfil');
    await page.getByTestId('nombre').fill('Ana QA');
    await page.getByTestId('telefono').fill('+34 600 000 000');
    // Tras el rediseño 2026-Q3 el botón es #guardar-cambios (antes #guardar)
    await page.locator('#guardar-cambios').click();
    await expect(page.getByTestId('toast-exito')).toContainText('Perfil actualizado');
  });
});
""",
    },
    {
        "path": "tests/login.cy.ts",
        "framework": "cypress",
        "domain": "autenticacion",
        "content": """describe('login', () => {
  it('usuario registrado inicia sesión', () => {
    cy.visit('/login');
    cy.get('[data-testid=email]').type(Cypress.env('QA_USER'));
    cy.get('[data-testid=password]').type(Cypress.env('QA_PASS'), { log: false });
    cy.get('[data-testid=submit]').click();
    cy.url().should('include', '/cuenta');
    cy.get('[data-testid=saludo]').should('contain', 'Hola');
  });

  it('credenciales inválidas muestran error sin filtrar detalle', () => {
    cy.visit('/login');
    cy.get('[data-testid=email]').type('noexiste@example.com');
    cy.get('[data-testid=password]').type('incorrecta');
    cy.get('[data-testid=submit]').click();
    cy.get('[data-testid=error]').should('contain', 'Credenciales no válidas');
  });
});
""",
    },
    {
        "path": "tests/export_csv.spec.ts",
        "framework": "playwright",
        "domain": "informes",
        "content": """import { test, expect } from '@playwright/test';

test('exportación CSV del panel admin llega completa', async ({ page, request }) => {
  await page.goto('/admin/informes');
  await page.getByTestId('exportar-csv').click();
  // La exportación es asíncrona: poll del job hasta 'completed' (máx 60 s)
  await expect(page.getByTestId('estado-export')).toHaveText('completed', { timeout: 60_000 });
  const download = await page.waitForEvent('download');
  const path = await download.path();
  // Validación contra la API: mismas filas que el listado
  const res = await request.get('/api/admin/productos/count');
  const { total } = await res.json();
  expect((await require('fs').promises.readFile(path, 'utf8')).split('\\n').length - 2).toBe(total);
});
""",
    },
]

# Los 4 curados a mano (checkout, el corazón del guion) + uno por cada fichero
# donde ocurre un fallo del catálogo.
TEST_ASSETS = [*_TEST_ASSETS_CURADOS, *ASSETS_POR_PROYECTO]


# Propuestas PENDIENTES de revisión: la bandeja de "Conocimiento → Capturar" no
# puede estar vacía, porque el lazo del producto es justamente ese — el sistema
# propone una lección a partir de lo que ha visto y una persona la aprueba.
# Cada una nace de un defecto real del catálogo.
PROPUESTAS = [
    {
        "kind": "leccion",
        "title": "Los timeouts de la pasarela se concentran en la ventana de conciliación",
        "challenge": "Tres tests de api-pagos fallaron a la vez por ETIMEDOUT y se abrió "
                     "incidencia contra el equipo de pagos.",
        "approach": "Al cruzar las horas de fallo con la ventana de conciliación del "
                    "proveedor, coinciden. No es el test: es la ventana.",
        "outcome": "Reprogramar la suite de pagos fuera de esa franja y, si no es posible, "
                   "marcar los fallos de esa ventana como infraestructura.",
        "domain": "pagos",
        "tags": ["infra", "pasarela", "conciliacion"],
        "family_keywords": ("test_pasarela", "gateway"),
    },
    {
        "kind": "leccion",
        "title": "Los selectores por id se rompen en cada rediseño del checkout",
        "challenge": "Tres incidencias distintas de localizador en checkout y perfil tras "
                     "cambios de maquetación.",
        "approach": "Los tests que usan data-testid sobrevivieron al rediseño; los que "
                    "usan id o clases, no.",
        "outcome": "Migrar los selectores críticos a data-testid antes del próximo "
                   "rediseño y añadirlo a la revisión de PR.",
        "domain": "checkout",
        "tags": ["maintenance", "selectores", "buenas-practicas"],
        "family_keywords": ("test_boton_finalizar", "finalizar"),
    },
    {
        "kind": "leccion",
        "title": "El cálculo de días de vacaciones no contempla los festivos locales",
        "challenge": "El test de vacaciones esperaba 12 días laborables y el sistema "
                     "calculó 14.",
        "approach": "El calendario de festivos que usa el cálculo es el nacional; los "
                    "festivos autonómicos no entran.",
        "outcome": "Cargar el calendario por centro de trabajo y cubrirlo con un caso "
                   "por comunidad.",
        "domain": "rrhh",
        "tags": ["real", "calculo", "festivos"],
        "family_keywords": ("test_solicitud_vacaciones", "working days"),
    },
    {
        "kind": "leccion",
        "title": "Reintentar un cobro con la misma clave de idempotencia lo duplica",
        "challenge": "Un reintento generó dos cargos con la misma clave de idempotencia.",
        "approach": "La clave se guarda tras confirmar el cobro, no antes: entre ambos "
                    "momentos hay ventana para duplicar.",
        "outcome": "Registrar la clave al recibir la petición, dentro de la misma "
                   "transacción que el cargo.",
        "domain": "pagos",
        "tags": ["real", "idempotencia", "critico"],
        "family_keywords": ("test_idempotencia", "idempotency"),
    },
    {
        "kind": "leccion",
        "title": "La sesión sigue aceptando el token después de cerrar sesión",
        "challenge": "Tras el logout, el token anterior seguía siendo válido contra la API.",
        "approach": "El cierre de sesión limpia la cookie en el navegador pero no invalida "
                    "el token en servidor.",
        "outcome": "Invalidar en servidor al cerrar sesión y cubrirlo con un test de "
                   "seguridad en cada release.",
        "domain": "acceso",
        "tags": ["real", "seguridad", "sesion"],
        "family_keywords": ("test_cerrar_sesion", "logout"),
    },
]

