# Guion del vídeo — Mnemo (María se va, Pablo llega · ~2:50)

Vídeo de demostración con voz en off sintética (ElevenLabs) sobre una grabación de pantalla
de **producción**. Es la versión grabada de `guion.md` (la demo en vivo, ~5 min): misma
historia, mismos datos, más corta.

- **Duración objetivo:** 2:30–3:00.
- **Formato:** 1920×1080, 30 fps. Navegador a pantalla completa, zoom al 125 %.
- **Voz:** una sola, en castellano de España, tono sereno y cercano. Ritmo de referencia:
  ~2,4 palabras por segundo (las duraciones de abajo salen de ahí).
- **Música:** opcional, muy baja, sin letra.

---

## Antes de grabar

- [ ] Despertar el backend un par de minutos antes (`/v2/health`): en plan gratuito se duerme.
- [ ] Sesión iniciada con la cuenta dueña de «Demo MTP».
- [ ] **Ocultar el email de la cabecera** (o recortarlo en edición).
- [ ] Ensayar las dos preguntas del Acto 3 justo antes: la respuesta del LLM cambia de una
      vez a otra. Grabar una toma buena; la voz no lee la respuesta, la resume.
- [ ] Preparar el enlace del acta **manipulado** (`runbook.md` §1c-bis) en una pestaña aparte.
- [ ] Cursor visible y movimientos lentos; nada de scroll rápido.

Emitir el acta en el Acto 2 escribe en producción: crea un acta nueva y pasa a ser la
«última» de `checkout-suite`. Es inofensivo, pero si no quieres tocar nada, graba la escena
con el formulario ya rellenado y salta al enlace del acta ya emitida (el de la sección
«Pruébalo» del [README](../../README.md)).

---

## Escenas

| # | Tiempo | En pantalla | Voz (resumen) |
|---|---|---|---|
| 1 | 0:00–0:25 | Portada: logo de Mnemo y el lema «La memoria del proyecto que se queda cuando un consultor rota». Fundido a la app. | El problema |
| 2 | 0:25–1:10 | `/app/continuity` → mapa de riesgo de rotación. Señalar `checkout-suite` (85, «Cubierto»: ≥ 80) y bajar despacio por su desglose. Clic en `banca-movil` (25, «Riesgo alto»: < 50). | El índice por proyecto |
| 3 | 1:10–1:42 | Con `checkout-suite`: escribir «María» en *Quién se va* y «Pablo» en *Quién llega* → **Emitir acta de traspaso** → **Copiar enlace de verificación** → abrirlo en una ventana sin sesión (o en el móvil, grabado aparte): sello del traspaso. Luego la pestaña del enlace manipulado: **Firma NO válida**. | El acta firmada |
| 4 | 1:42–2:12 | **Conocimiento** → pestaña **Preguntar**: «¿Por qué es inestable el checkout?» → respuesta con sus fuentes. Después «¿A quién pregunto por el sandbox del PSP?» → equipo de Pagos. | Pablo pregunta |
| 5 | 2:12–2:36 | **Dashboard** → *Runs recientes* → un run con fallos de `tienda-online`: veredictos con la regla que decidió cada uno y su acta. | De dónde sale la memoria |
| 6 | 2:36–2:52 | Vuelta al mapa de riesgo. Fundido a la portada con la URL `mnemo-beta-one.vercel.app`. | Cierre |

---

## Texto para ElevenLabs

Un bloque por escena: genera cada uno como un clip aparte y así cada toma se ajusta a su voz.
Está escrito para leerse en voz alta: sin siglas, sin código y con los números en letra.

**Escena 1 — El problema (~24 s)**

> En una consultora de testing, los consultores rotan de un cliente a otro. Y cuando alguien
> se va de un proyecto, con él se va lo que nunca llegó a escribirse: cómo se levanta el
> entorno, a quién se pregunta cuando algo se cae, y por qué un test que parece inestable,
> en realidad, no lo es.

**Escena 2 — El índice (~44 s)**

> Mnemo es la memoria de ese proyecto. Y empieza por medir cuánto sabe de cada uno.
> Este es el mapa de riesgo de rotación: todos los proyectos, del más expuesto al más cubierto.
> Checkout Suite tiene un índice de ochenta y cinco sobre cien. No es una opinión: es un
> recuento, con su desglose a la vista. Los fallos que se repiten y lo que el equipo aprendió
> de ellos, el porqué de cada etiqueta, y el oficio del proyecto.
> Banca Móvil se queda en veinticinco. Si mañana rota quien lo lleva, esto es lo que se pierde.
> Y ahora se ve antes, no después.

**Escena 3 — El acta (~30 s)**

> María, la responsable de Checkout Suite, se va a otro cliente. Llega Pablo.
> Mnemo emite un acta de traspaso firmada: el índice, quién se va, quién llega, y una huella
> de todo el conocimiento que queda depositado. Si mañana se borra algo, Mnemo lo avisa.
> El acta viaja en un enlace. Cualquiera la comprueba, sin cuenta en Mnemo.
> Y si alguien cambia un solo dato, la firma deja de ser válida.

**Escena 4 — Pablo pregunta (~27 s)**

> Pablo no tiene que perseguir a María. Pregunta con sus palabras.
> ¿Por qué es inestable el checkout?
> Mnemo responde con lo que María dejó escrito, incluida la razón que tecleó al etiquetar
> esos fallos, sin saber que estaba escribiendo para su sustituto.
> Y cada respuesta dice de dónde sale.
> ¿A quién pregunto por el sandbox del PSP? Al equipo de Pagos, y por qué canal.

**Escena 5 — De dónde sale (~22 s)**

> Esta memoria no sale de una sesión de documentación que nadie hace. Sale del trabajo de cada
> día. Cada ejecución de la integración continua entra en Mnemo, un motor de reglas clasifica
> cada fallo y dice qué regla aplicó. La inteligencia artificial solo desempata los casos
> dudosos, y una persona lo aprueba.

**Escena 6 — Cierre (~13 s)**

> Una wiki no sabe qué test falló ayer. Mnemo sí.
> Por eso su memoria se llena con el trabajo, y se puede firmar.
> Cuando un consultor rota, el conocimiento se queda.

381 palabras: ~2:40 de voz a 2,4 palabras por segundo; con las pausas entre escenas, ~2:50.
En la escena 4 la respuesta del LLM tarda unos segundos en aparecer: dejar que la voz
formule la pregunta mientras se escribe y acelerar la espera en edición.

---

## Pronunciación

Revisarla en la primera generación. Si una palabra suena mal, ElevenLabs permite fijarla con
un diccionario de pronunciación (alias) sin tocar el texto.

| Palabra | Cómo debe sonar | Si falla |
|---|---|---|
| Mnemo | «Némo» (la *m* inicial es muda, como en *mnemotecnia*) | alias → «Nemo» |
| Checkout Suite | en inglés: «chékaut suit» | alias → «chécaut suit» |
| Banca Móvil | en castellano | — |
| sandbox | en inglés: «sándbox» | — |
| PSP | letra a letra: «pe ese pe» (la pasarela de pago) | alias → «pe ese pe» |
| Pagos | nombre del equipo; leve énfasis | — |

En pantalla sí aparecen `checkout-suite` y `banca-movil` con guion: la voz los dice como
nombres, sin leer el guion.

---

## De dónde sale cada afirmación de la voz

Las afirmaciones son las de `guion.md` (tabla «De dónde sale cada afirmación»). Las propias
de este vídeo:

| Lo que dice la voz | Fuente | Comprobado |
|---|---|---|
| 85 en Checkout Suite, 25 en Banca Móvil | `compute_index` sobre Demo MTP en prod | 2026-10-01 |
| «No es una opinión: es un recuento» | `src/continuity/index.py`: solo lecturas y una media ponderada de 4 dimensiones | código |
| El acta firma el índice, quién se va, quién llega y una huella de todo lo depositado | `mnemo.traspaso.v2` (`src/continuity/service.py`, `manifest.py`): `traspaso.de/para` + `contenido.sha256` (raíz de las huellas de cada elemento) | código + acta de prod 2026-10-01 |
| «Si mañana se borra algo, Mnemo lo avisa» | `service.py::_integridad` → «El conocimiento ha cambiado desde el acta» en `/app/continuity` | código |
| Se comprueba con un enlace, sin cuenta | `/verify` fuera de `/app`; `POST /v2/certificates/verify` público | E2E `verify.spec.ts` |
| Si se cambia un solo dato, la firma deja de ser válida | E2E: el acta con el índice retocado da «Firma NO válida» | 2026-10-01 |
| Responde con lo que dejó María y dice de dónde sale | `answer_over_sources` (cita ids); ensayo con Groq de las preguntas | 2026-10-01 |
| La razón tecleada al etiquetar llega a la respuesta | La razón de María («Los timeouts correlan con runners fríos…», etiquetada el 2026-07-15) sale entre las fuentes de la pregunta del checkout; tiene su propio vector (migración `030`) | ensayo 2026-10-01 |
| El equipo de Pagos y su canal | Contacto «El sandbox del PSP lo lleva el equipo de Pagos» (#pagos-soporte) | ensayo 2026-10-01 |
| Un motor de reglas clasifica y dice qué regla aplicó | `src/triage/engine.py` (`rule_applied` en cada veredicto) | código |
| La IA solo desempata los dudosos y una persona lo aprueba | R6 → `ambiguous`; el desempate deja `requires_approval=True` (`src/triage/service.py`) | código |

**No decir en la voz** (no se puede comprobar en el producto): tiempos («en segundos»),
ahorros, porcentajes de acierto, ni que Mnemo lo usa ya algún equipo.
