# Guion de demo — Mnemo (María se va, Pablo llega · ~5 min)

Demo contra el despliegue de **producción** (frontend en Vercel + backend en el Space +
Supabase), con la cuenta dueña de la organización **«Demo MTP»**. La operativa (URLs,
credenciales, comandos con valores reales) vive en `runbook.md` y, para los valores
privados, en `prod.local.md` (local, no versionado).

**La historia:** María, la QA senior de `checkout-suite`, rota a otro cliente. Pablo la
sustituye. Mnemo es lo que hace que lo que sabía María no se vaya con ella.

---

## Tabla de tiempos

| Bloque | Contenido | Duración |
|---|---|---|
| Apertura | El dolor: lo que se va con el consultor que rota | 30 s |
| Acto 1 | Índice de continuidad: cuánto sabe Mnemo de cada proyecto | 60 s |
| Acto 2 | Acta de traspaso firmada y verificable sin cuenta | 75 s |
| Acto 3 | Pablo pregunta; Mnemo responde con lo que dejó María, citado | 75 s |
| Acto 4 | De dónde sale la memoria: el día a día de los runs | 45 s |
| Cierre | Por qué esto no es una wiki con IA | 15 s |
| **Total** | | **~5 min** |

---

## Apertura (30 s)

> «En una consultora de QA, los consultores rotan. Cuando María deja `checkout-suite`, con
> ella se van cosas que no están en ningún sitio: cómo se levanta el entorno, qué tarjetas
> de prueba usar, a quién se le escribe cuando el sandbox del PSP se cae, y por qué un test
> que parece inestable en realidad no lo es. El que llega lo aprende a base de preguntar…
> si María sigue contestando.»

---

## Acto 1 — Cuánto sabe Mnemo de cada proyecto (60 s)

**Qué se hace:** abrir `/app/continuity?project=checkout-suite` (marcador preparado: sin el
parámetro, la vista abre en el primer proyecto por orden alfabético).

1. `checkout-suite` → índice **95**. Recorrer el desglose: *el porqué de las etiquetas*
   4/4, *oficio del proyecto* 4/4 (runbook, datos de prueba, contactos, decisiones),
   *reglas con respaldo* 4/5.
2. Cambiar a `banca-movil` → índice **25**: *oficio* 0/4, *reglas con respaldo* 0/2.

> «El índice no es una opinión: es el recuento de lo que la memoria tiene de cada
> proyecto, con el desglose a la vista. `checkout-suite` está documentado; si mañana rota
> quien lleva `banca-movil`, esto es lo que se pierde — y ahora se ve antes, no después.»

**Mensaje:** el riesgo de rotación pasa de intuición a dato por proyecto.

---

## Acto 2 — El acta de traspaso (75 s)

**Qué se hace:** en la misma vista, con `checkout-suite` seleccionado.

1. **«Emitir acta de traspaso»** (requiere rol owner/admin) → el acta queda firmada con
   el índice y su desglose dentro.
2. **«Copiar enlace de verificación»** → abrirlo en una ventana **sin sesión** (mejor: en
   el móvil, delante de todos). La página `/verify` comprueba la firma y pinta el sello del
   traspaso: proyecto, índice y fecha.
3. El enlace **manipulado** (preparado de antemano, ver `runbook.md` §1c-bis — vale el
   mismo procedimiento con un enlace de traspaso) → **«Firma NO válida»**.

> «Esto es lo que la consultora entrega al cliente cuando rota a una persona: no un "ya se
> lo he contado a Pablo", sino un acta firmada de qué conocimiento quedó depositado.
> Cualquiera la verifica sin cuenta en Mnemo. Y si alguien la toca, se nota.»

**Mensaje:** une los dos pilares — memoria del proyecto y evidencia firmada.

---

## Acto 3 — Pablo pregunta (75 s)

**Qué se hace:** menú **Onboarding al proyecto** → «Preguntar a la memoria» (o
**Conocimiento** → pestaña «Preguntar»).

1. *«¿Por qué es inestable el checkout?»* → la respuesta tira de la lección del
   rate-limit del sandbox del PSP y de la razón con la que se etiquetó la familia de
   timeouts («los timeouts correlan con runners fríos y latencia del sandbox del PSP, no
   con el test»), con sus citas.
2. *«¿A quién pregunto por el sandbox del PSP?»* → el contacto: lo lleva el equipo de
   Pagos.
3. (Si sobra tiempo) *«¿Cómo levanto el entorno de checkout?»* → el runbook.

> «Pablo no tiene que encontrar a María. Pregunta con sus palabras y recibe lo que ella
> dejó escrito — incluida la razón que tecleó al etiquetar un fallo hace semanas, sin
> saber que estaba escribiendo para su sustituto. Cada respuesta dice de dónde sale.»

**Si el LLM no responde:** la respuesta degrada a la lista de fuentes relevantes, y se
dice: «sin IA, sigue diciéndote dónde mirar».

---

## Acto 4 — De dónde sale la memoria (45 s)

**Qué se hace:** **Dashboard** → «Runs recientes» → un run **con fallos** (los semanales de
`checkout-suite` son verdes a propósito; vale uno de `tienda-online`, o el push en vivo hecho
después del Acto 2) → se abre ese run: veredictos de triaje, con la regla que decidió cada uno,
y su acta.

> «Esta memoria no se rellena en una sesión de documentación que nadie hace. Sale del día a
> día: cada run del CI entra, el motor determinista clasifica cada fallo y explica qué regla
> aplicó, el equipo etiqueta con una frase, y esa frase se vuelve buscable. Cada run lleva
> además su propia acta firmada.»

Detalle para preguntas (no en el guion principal): si una familia marcada *flaky* empieza a
fallar con una aserción pura, el motor no la esconde tras la etiqueta — marca «contradice la
etiqueta humana» y pide revisión antes de dar el run por bueno.

---

## Cierre (15 s)

> «Una wiki no sabe qué test falló ayer; Mnemo sí, y por eso su memoria se llena sola y se
> puede firmar. Cuando un consultor rota, el conocimiento se queda. Gracias.»

---

## De dónde sale cada afirmación

Revisar esta tabla antes de cada ensayo: si el producto cambia, el guion también.

| Afirmación | Fuente | Comprobado |
|---|---|---|
| `checkout-suite` 95 / `banca-movil` 25 y sus desgloses | `compute_index` sobre Demo MTP en prod (`src/continuity/index.py`) | 2026-10-01 |
| El índice es un recuento recalculable, no una opinión | `index.py`: solo lecturas, media ponderada de 4 dimensiones con num/den; sin datos → `None`, no 0 | código |
| Emitir el acta requiere owner/admin | `src/continuity/service.py::emit_handover` (PermissionError) | código |
| El acta lleva el índice y el desglose dentro, firmada | `emit_handover`: payload con `continuity.score`, `dimensions`, `inventario`, `key_id`; `sign(canonical_json(...))` | código |
| Se verifica sin cuenta | `frontend/src/app/verify/page.tsx` (fuera de `/app`, sin sesión) | código |
| Enlace manipulado → firma no válida | `runbook.md` §1c-bis (probado con actas de release) | ensayar con traspaso |
| Las preguntas recuperan la lección del PSP, la razón de la familia, el contacto y el runbook | `search_unified` sobre Demo MTP en prod (fuentes, sin LLM) | 2026-10-01 |
| La razón tecleada al etiquetar se vuelve buscable | PR #114 (vector propio de la razón; media con el centroide) | prod, 2026-10-01 |
| Cada respuesta cita sus fuentes; sin LLM degrada a fuentes | `src/ai/nl_query.py::answer_over_sources` | código |
| Texto exacto de la respuesta del LLM | Gemini en prod — **no determinista: ensayar en la app** | pendiente |
| «Contradice la etiqueta humana» | PR #113 (`R0_prior_contradicted`) | en prod (01-10) |
| El acta da fe del análisis, no de que se ejecutaran los tests | disclaimer firmado (`src/certify/certificate.py::_DISCLAIMER`) y texto del sello en `/verify` | código |

**Retirado del guion anterior** por no poder sostenerlo: «coste de API 0 €» (depende del
plan del proveedor de LLM), «100 % on-premise con Ollama» (no es la configuración que se
usa) y cualquier tiempo concreto («en segundos»). La cifra de «2-6 semanas de shadowing por
traspaso» de la auditoría del 12-ago **no está medida**: no decirla como dato.

---

## Notas de presentación

- Narrar la historia de María y Pablo, no las pantallas: cada transición responde a una
  pregunta de Pablo.
- La demo corre en la nube con un LLM de API (Gemini). El proveedor es configurable; no
  afirmar dónde viajan los datos más allá de eso.
- Plan B y checklist previa: `runbook.md`. Si el acta de traspaso falla en vivo, enseñar la
  última emitida (`handover/latest`) desde el ensayo.
