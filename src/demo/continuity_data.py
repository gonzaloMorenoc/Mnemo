"""El escenario María→Pablo: el oficio de checkout-suite (auditoría 12-ago, paso 3).

María es la QA senior que lleva checkout-suite y rota a otro cliente. Estos 9 items
son lo que un reemplazo necesita la primera semana y lo que el CHECK de la 018
rechazaba hasta los kinds operativos (#106): cómo se levanta el entorno, con qué se
prueba, a quién se pregunta y qué se acordó NO hacer.

Solo datos. La siembra vive en seed_continuity.py y es idempotente por título.
"""

_PROJECT = "checkout-suite"

CONTINUITY_ITEMS = [
    # ------------------------------------------------------------------ runbooks
    {
        "kind": "runbook",
        "title": "Levantar el entorno de checkout con el sandbox del PSP",
        "challenge": "El entorno local necesita el simulador de autorizaciones del PSP; sin él, todo pago se queda en 'pendiente' y la suite entera falla en cascada.",
        "approach": "docker compose up (perfil checkout) → exportar PSP_SANDBOX_URL y PSP_SANDBOX_KEY (vault del proyecto, entrada 'psp-sandbox') → arrancar el simulador de callbacks con `make psp-sim` → smoke: un pago con la tarjeta de prueba aprobada debe confirmar en menos de 10 s.",
        "outcome": "Entorno reproducible en unos 5 minutos; antes era la primera media mañana de cada incorporación.",
        "domain": "checkout",
        "tags": ["entorno", "psp", "onboarding"],
        "project": _PROJECT,
    },
    {
        "kind": "runbook",
        "title": "Relanzar la suite de checkout tras un despliegue",
        "challenge": "Relanzar a mano tras cada deploy provocaba dobles ejecuciones y falsos rojos cuando el despliegue aún estaba a medias.",
        "approach": "Esperar al check de salud del deploy (job 'post-deploy-health') → relanzar SOLO el job 'e2e-checkout', nunca el pipeline entero → si el deploy quedó a medias (health en ámbar), NO relanzar: el rojo sería del entorno, no del código.",
        "outcome": "Cero dobles ejecuciones desde que el runbook existe.",
        "domain": "infra-ci",
        "tags": ["ci", "despliegue"],
        "project": _PROJECT,
    },
    # -------------------------------------------------------------- datos de prueba
    {
        "kind": "dato_prueba",
        "title": "Tarjetas del sandbox del PSP",
        "challenge": "Cada tarjeta de prueba fuerza una respuesta distinta del PSP; usar la equivocada hace pasar tests que deberían fallar.",
        "approach": "4111 1111 1111 1111 → autorización aprobada (flujo feliz). 4000 0000 0000 0002 → rechazada por el emisor (para los tests de anulación). CVV y fecha: cualesquiera válidos. Son los números de prueba PÚBLICOS del sandbox; jamás usar una tarjeta real, ni siquiera caducada.",
        "outcome": None,
        "domain": "pagos",
        "tags": ["sandbox", "psp", "datos"],
        "project": _PROJECT,
    },
    {
        "kind": "dato_prueba",
        "title": "Usuarios de prueba de checkout",
        "challenge": "Los tests de dirección y stock necesitan usuarios en estados concretos; crearlos al vuelo hacía los tests lentos y frágiles.",
        "approach": "comprador-completo (dirección y consentimientos completos, para el flujo feliz) · comprador-sin-stock (su carrito apunta al SKU sin existencias, para reservas) · carga-k6 (reservado a los tests de carga; NO usarlo en e2e, ensucia sus métricas). Se reponen con la ventana nocturna de Plataforma.",
        "outcome": None,
        "domain": "checkout",
        "tags": ["usuarios", "datos"],
        "project": _PROJECT,
    },
    # ------------------------------------------------------------------ contactos
    {
        "kind": "contacto",
        "title": "El sandbox del PSP lo lleva el equipo de Pagos",
        "challenge": "Cuando el sandbox se cae o rate-limita, abrir un ticket genérico tardaba días.",
        "approach": "Canal #pagos-soporte (responden en horario CET). Pedirles: resets del sandbox, ampliar el rate-limit en ventanas de carga, altas de claves. NO pedirles: datos de tarjetas reales (no existen en sandbox) ni cambios del simulador local, que es nuestro.",
        "outcome": None,
        "domain": "pagos",
        "tags": ["equipo", "psp"],
        "project": _PROJECT,
    },
    {
        "kind": "contacto",
        "title": "Los datos de staging los repone el equipo de Plataforma",
        "challenge": "Tests que dependían de datos agotados fallaban hasta que alguien descubría a quién pedir la reposición.",
        "approach": "Canal #plataforma. La reposición corre cada noche a las 03:00 CET; si un test agota datos a media tarde, pedir reposición manual ahí (tarda unos 15 min). Los usuarios de prueba de checkout entran en esa ventana.",
        "outcome": None,
        "domain": "infra-ci",
        "tags": ["equipo", "staging"],
        "project": _PROJECT,
    },
    # ------------------------------------------------------------------ decisiones
    {
        "kind": "decision",
        "title": "Acordado con el cliente NO automatizar el 3DS real",
        "challenge": "El challenge 3DS real exige un OTP por SMS y cada transacción del entorno certificado cuesta dinero: automatizarlo era caro y frágil.",
        "approach": "Se prueba con el simulador del PSP (cubre aprobado, rechazado y timeout del challenge). El 3DS real se verifica a mano una vez por release, con la tarjeta de prueba del banco en el móvil del equipo. Acordado con el cliente en el comité de mayo de 2026.",
        "outcome": "Ahorro de unos 40 min por pipeline y cero flaky por OTP; el riesgo residual quedó aceptado por escrito.",
        "domain": "pagos",
        "tags": ["alcance", "3ds", "cliente"],
        "project": _PROJECT,
    },
    {
        "kind": "decision",
        "title": "Los tests de concurrencia de stock corren solo en la nocturna",
        "challenge": "Las reservas de stock de los tests de concurrencia interferían con las suites de PR y producían rojos cruzados imposibles de triar.",
        "approach": "Job 'stock-concurrencia' programado a las 02:00, fuera de la ventana de reposición de datos. En PR solo corre el test unitario de la reserva. Acordado en la retro de junio de 2026.",
        "outcome": "Desaparecieron los rojos cruzados de las suites de PR.",
        "domain": "checkout",
        "tags": ["concurrencia", "planificacion"],
        "project": _PROJECT,
    },
    # -------------------------------------------------------------------- lección
    {
        "kind": "leccion",
        "title": "Los fallos intermitentes del sandbox del PSP se diagnostican por el rate-limit",
        "challenge": "Timeouts intermitentes en checkout parecían flaky del test; se perdían horas re-ejecutando.",
        "approach": "Mirar primero la cabecera X-RateLimit-Remaining del sandbox en el log del simulador: si está a cero, el fallo es el límite de 30 peticiones/minuto (ver el riesgo documentado), no el test. Espaciar la suite o pedir ampliación en #pagos-soporte.",
        "outcome": "El triaje de estos timeouts pasó de horas a minutos; la etiqueta 'infra' de la familia de timeouts lleva esta razón.",
        "domain": "pagos",
        "tags": ["psp", "rate-limit", "triaje"],
        "project": _PROJECT,
    },
]
