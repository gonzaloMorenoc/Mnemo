# Guion del vídeo — Mnemo (María se va, Pablo llega · 2:34)

Vídeo de demostración con voz en off sintética (ElevenLabs) sobre una grabación de pantalla
de **producción**. Es la versión grabada de `guion.md` (la demo en vivo, ~5 min): misma
historia, mismos datos, más corta.

- **Duración:** 2:34 en la versión montada.
- **Formato:** 1920×1080, 30 fps. Navegador a 1280×720 con zoom al 150 %. Fundidos cruzados de
  0,5 s entre planos y escenas; voz normalizada a −16 LUFS.
- **Voz:** una sola, en castellano de España, tono sereno y cercano. Ritmo de referencia:
  ~2,6 palabras por segundo (las duraciones de abajo son las de las voces generadas).
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

Emitir el acta en la escena 3 escribe en producción: crea un acta nueva y pasa a ser la
«última» de `checkout-suite`. La versión montada no la emite: graba el formulario ya
rellenado y salta al enlace del acta ya emitida (el de la sección «Pruébalo» del
[README](../../README.md)).

Si se graba con Playwright, `recordVideo` captura a la resolución CSS del viewport (no aplica
`deviceScaleFactor`) y rellena de gris hasta el tamaño pedido: recortar la zona útil antes de
escalar a 1080p.

---

## Escenas

| # | Tiempo | En pantalla | Voz (resumen) |
|---|---|---|---|
| 1 | 0:00–0:22 | Portada: lema «Cuando un consultor rota, el conocimiento se queda.» resaltado; baja a las tarjetas «Memoria que se llena trabajando» y «Se enchufa a tu CI». | El problema |
| 2 | 0:21–1:01 | `/app/continuity` → mapa de riesgo de rotación. Pasar por `banca-movil` y `tienda-online`, clic en `checkout-suite` (85, «Cubierto»: ≥ 80) y resaltar su desglose fila a fila. Clic en `banca-movil` (25, «Riesgo alto»: < 50). | El índice por proyecto |
| 3 | 1:00–1:32 | Con `checkout-suite`: «María (QA senior)» en *Quién se va* y «Pablo» en *Quién llega*, cursor sobre **Emitir acta de traspaso** (sin pulsarlo). Corte a `/verify` con el acta ya emitida, sin sesión: 85, quién se va y quién llega, la huella de los 26 elementos, el sello y «Sin cuenta». Después el mismo enlace manipulado: **Firma NO válida**, con el rótulo «Mismo enlace, con el índice cambiado: 85 → 99». | El acta firmada |
| 4 | 1:32–1:59 | **Conocimiento** → pestaña **Preguntar**: «¿Por qué es inestable el checkout?» → respuesta con sus fuentes (resaltar la razón de María, tipo *Defecto*). Después «¿A quién pregunto por el sandbox del PSP?» → equipo de Pagos. | Pablo pregunta |
| 5 | 1:58–2:19 | **Autopilot** → *Runs recientes* → el run de `checkout-suite` con «3 fallos»: veredictos de triaje con la regla que decidió cada uno, acciones correctivas pendientes de aprobar y su acta. | De dónde sale la memoria |
| 6 | 2:19–2:34 | Vuelta al mapa de riesgo y al acta de `checkout-suite`. Fundido a la tarjeta final con el lema y la URL `mnemo-beta-one.vercel.app`. | Cierre |

---|---|---|---|
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

**Escena 1 — El problema (21 s)**

> En una consultora de testing, los consultores rotan de un cliente a otro. Y cuando alguien
> deja un proyecto, se lleva lo que nunca llegó a escribirse: los pasos para levantar el
> entorno, la persona a la que llamar cuando algo se cae, y el motivo por el que un test que
> parece inestable, en realidad, no lo es.

**Escena 2 — El índice (38 s)**

> Mnemo es la memoria de ese proyecto. Y empieza por medir cuánto sabe de cada uno.
> Este es el mapa de riesgo de rotación: todos los proyectos, del más expuesto al más cubierto.
> Checkout Suite tiene un índice de ochenta y cinco sobre cien. No es una opinión: es un
> recuento, con su desglose a la vista. Los fallos que se repiten y lo que el equipo aprendió
> de ellos, el porqué de cada etiqueta, y el oficio del proyecto.
> Banca Móvil se queda en veinticinco. Si mañana rota quien lo lleva, esto es lo que se pierde.
> Y ahora se ve antes, no después.

**Escena 3 — El acta (30 s)**

> María, la responsable de Checkout Suite, se va a otro cliente. Llega Pablo.
> Mnemo emite un acta de traspaso firmada: el índice, quién se va, quién llega, y una huella
> de todo el conocimiento que queda depositado. Si mañana se borra algo, Mnemo lo avisa.
> El acta viaja en un enlace, y cualquiera puede comprobarla, aunque no tenga cuenta en Mnemo.
> Si alguien cambia un solo dato, la firma deja de ser válida.

**Escena 4 — Pablo pregunta (26 s)**

> Pablo no tiene que perseguir a María. Pregunta con sus palabras.
> ¿Por qué es inestable el checkout?
> Mnemo responde con lo que María dejó escrito, incluida la razón que tecleó al etiquetar
> esos fallos, sin saber que estaba escribiendo para su sustituto.
> Y cada respuesta dice de dónde sale.
> ¿A quién pregunto por el sandbox del PSP? Al equipo de Pagos, en su canal de soporte.

**Escena 5 — De dónde sale (20 s)**

> Esta memoria no sale de una sesión de documentación que nadie hace. Sale del trabajo de cada
> día. Cada ejecución de la integración continua entra en Mnemo, un motor de reglas clasifica
> cada fallo y dice qué regla aplicó. La inteligencia artificial solo desempata los casos
> dudosos, y una persona lo aprueba.

**Escena 6 — Cierre (12 s)**

> Una wiki no sabe qué test falló ayer. Mnemo sí.
> Por eso su memoria se llena con el trabajo, y se puede firmar.
> Cuando un consultor rota, el conocimiento se queda.

386 palabras: 2:28 de voz (voz Mirna, modelo `eleven_multilingual_v2`); con las pausas
entre escenas, 2:34. En la escena 4 la respuesta del LLM tarda unos segundos en aparecer: la
versión montada corta la espera con un plano que ya tiene la respuesta cargada.

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
