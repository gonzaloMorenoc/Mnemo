# Guion de demo — Mnemo (María se va, Pablo llega · ~5 min)

Demo contra el despliegue de **producción** (frontend en Vercel, backend en un Hugging
Face Space y Supabase), con una cuenta administradora de la organización de demostración
**«Demo MTP»**, que tiene datos sembrados. Cómo está montada y qué preparar antes:
[`runbook.md`](runbook.md).

El acta de traspaso del Acto 2 se puede comprobar sin cuenta: el enlace está en la sección
«Pruébalo» del [README](../../README.md).

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

1. Arriba, el **mapa de riesgo de rotación**: todos los proyectos, del más expuesto al
   más cubierto. `checkout-suite` → índice **85** («Cubierto»). Recorrer el desglose:
   *memoria de defectos* 2/3 (los fallos que vuelven, con lo que el equipo aprendió de
   ellos — lo que una wiki no sabe), *el porqué de las etiquetas* 4/4, *oficio del
   proyecto* 4/4 (runbook, datos de prueba, contactos, decisiones), *reglas con respaldo*
   4/5. Señalar el hueco: el error de exportación CSV se repite y nadie ha dejado su
   lección («Revisar propuestas →»).
2. Cambiar a `banca-movil` → índice **25**: *oficio* 0/4, *reglas con respaldo* 0/2.

> «El índice no es una opinión: es el recuento de lo que la memoria tiene de cada
> proyecto, con el desglose a la vista. `checkout-suite` está documentado; si mañana rota
> quien lleva `banca-movil`, esto es lo que se pierde — y ahora se ve antes, no después.»

**Mensaje:** el riesgo de rotación pasa de intuición a dato por proyecto.

---

## Acto 2 — El acta de traspaso (75 s)

**Qué se hace:** en la misma vista, con `checkout-suite` seleccionado.

1. Rellenar **«Quién se va»** (María) y **«Quién llega»** (Pablo) y pulsar **«Emitir acta de
   traspaso»** (requiere ser administrador) → el acta queda firmada con el índice, su
   desglose, quién se va y quién llega, y la **huella del contenido**: los N elementos
   de conocimiento depositados, cada uno con su SHA-256.
2. **«Copiar enlace de verificación»** → abrirlo en una ventana **sin sesión** (mejor: en
   el móvil, delante de todos). La página `/verify` comprueba la firma y pinta el sello del
   traspaso: proyecto, índice, quién se va y quién llega, cuántos elementos y su huella.
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
| `checkout-suite` 85 / `banca-movil` 25 y sus desgloses | `compute_index` sobre Demo MTP en prod (`src/continuity/index.py`) | 2026-10-01 |
| El índice es un recuento recalculable, no una opinión | `index.py`: solo lecturas, media ponderada de 4 dimensiones con num/den; sin datos → `None`, no 0 | código |
| Emitir el acta requiere owner/admin | `src/continuity/service.py::emit_handover` (PermissionError) | código |
| El acta lleva el índice y el desglose dentro, firmada | `emit_handover`: payload con `continuity.score`, `dimensions`, `inventario`, `key_id`; `sign(canonical_json(...))` | código |
| Se verifica sin cuenta | `frontend/src/app/verify/page.tsx` (fuera de `/app`, sin sesión) | código |
| Enlace manipulado → firma no válida | E2E `frontend/e2e/verify.spec.ts` (el acta de traspaso con el índice retocado da «Firma NO válida»); procedimiento en `runbook.md` §1c-bis | E2E |
| Las preguntas recuperan la lección del PSP, la razón de la familia, el contacto y el runbook | `search_unified` sobre Demo MTP en prod (fuentes, sin LLM) | 2026-10-01 |
| La razón tecleada al etiquetar se vuelve buscable | `triage_corrections.reason_embedding` (migración `030`): la razón tiene su propio vector y la búsqueda de familias promedia su distancia con la del centroide | prod, 2026-10-01 |
| Cada respuesta cita sus fuentes; sin LLM degrada a fuentes | `src/ai/nl_query.py::answer_over_sources` | código |
| Las tres preguntas responden en español y citan la fuente correcta (PSP → lección del rate-limit; contacto → equipo de Pagos; entorno → runbook) | Ensayo contra Groq `gpt-oss-120b` con `KnowledgeService.ask` sobre Demo MTP (`generate_structured` exige JSON en el prompt, `src/ai/generate.py`) | 2026-10-01 |
| Texto exacto de la respuesta del LLM | Groq `gpt-oss-120b` en prod — **no determinista: ensayar en la app el día antes** | pendiente |
| «Contradice la etiqueta humana» | `src/triage/engine.py` (`R0_prior_contradicted`) | en prod (01-10) |
| El acta firma la huella del contenido y quién se va/llega; Mnemo detecta si cambió | `src/continuity/manifest.py`, `service.py::_integridad` | código |
| Rotar la clave no invalida actas (con la pública anterior declarada como retirada) | `CertificateService.verify_payload` (anillo por `key_id`, `MNEMO_SIGNING_RETIRED_PUBLIC_KEYS`) | código |
| El índice no se infla con notas vacías | `src/continuity/index.py` (MIN_RAZON_CHARS, MIN_CONTENIDO_CHARS, MIN_DIMENSIONES_MEDIBLES) | código |
| Memoria de defectos 2/3 en checkout-suite | `src/demo/seed_recurrencia.py` + `compute_index` en prod | 2026-10-01 |
| El acta da fe del análisis, no de que se ejecutaran los tests | disclaimer firmado (`src/certify/certificate.py::_DISCLAIMER`) y texto del sello en `/verify` | código |

**Qué no se afirma**, porque no se puede comprobar en el producto: un coste de API concreto
(depende del plan del proveedor de LLM), que la demo corra en local (usa un LLM de API),
tiempos («en segundos») ni ahorros por traspaso, que no están medidos.

---

## Notas de presentación

- **«¿Y si mañana se borra la memoria?»** → bajo la última acta, Continuidad recalcula la
  huella: «lo depositado sigue intacto» o «ha cambiado desde el acta (N → M elementos)».
- **«¿Y cuando rotéis la clave de firma?»** → las actas llevan el `key_id` firmado y la
  verificación elige la clave por él entre la actual y las retiradas
  (`MNEMO_SIGNING_RETIRED_PUBLIC_KEYS`): rotar no invalida lo emitido mientras la pública
  anterior siga declarada.
- **«¿Esto está sembrado?»** → sí, y decirlo antes de que lo pregunten: es una
  organización de demostración con datos sembrados por el mismo camino que la app
  (ingesta del CI, triaje del motor, etiquetas con su razón). Con datos reales la memoria
  se llena igual —cada run y cada etiqueta—, y lo que todavía no está medido es el
  ahorro: es el objetivo del piloto.
- **«Inflo el índice con notas vacías»** → no: una razón cuenta desde ~20 caracteres, un
  tipo de oficio solo si tiene contenido, y con menos de dos dimensiones medibles el
  índice dice «sin datos suficientes». Mide qué hay documentado, no su calidad (el sello
  lo dice), y una regla sin respaldo baja el índice a propósito: es un hueco.

- Narrar la historia de María y Pablo, no las pantallas: cada transición responde a una
  pregunta de Pablo.
- La demo corre en la nube con un LLM de API (`gpt-oss-120b` en Groq). El proveedor es configurable; no
  afirmar dónde viajan los datos más allá de eso.
- Plan B y checklist previa: `runbook.md`. Si el acta de traspaso falla en vivo, enseñar la
  última emitida (`handover/latest`) desde el ensayo.
