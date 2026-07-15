# Guion de demo — Mnemo (3 actos, ~4 min)

Demo contra el despliegue de **producción** (frontend en Vercel + backend en la nube + Supabase).
La operativa (URLs concretas, credenciales, comandos con valores reales) vive en `runbook.md` y,
para los valores privados, en `prod.local.md` (archivo local, no versionado).

---

## Tabla de tiempos

| Acto | Contenido | Duración aprox. |
|------|-----------|-----------------|
| Apertura | Problema y propuesta | 30 s |
| Acto 1 | Push en vivo → triaje automático + run real bloqueado | 60 s |
| Acto 2 | Self-heal + aprobación humana + acta firmada + verificación pública | 90 s |
| Acto 3 | Calibración (foso) + aislamiento multi-cliente + ROI | 60 s |
| Cierre | Diferenciadores y call to action | 15 s |
| **Total** | | **~4 min** |

---

## Frase de apertura

> "Un cambio de botón en la UI rompe el test de perfiles — y el equipo de QA pierde la mañana
> averiguando por qué. Mnemo lo detecta en automático, propone el parche exacto y, con una firma
> humana, emite un **acta criptográfica que cualquiera puede verificar**. Sin coste de API,
> con el LLM configurable 100% on-premise para clientes con datos sensibles."

---

## Acto 1 — El problema (push en vivo → triaje automático)

### Qué se dice

> "Esto es Mnemo en producción, con la organización 'Demo MTP' y los runs del sprint ya
> procesados. Ahora llega un push del CI: el botón 'Guardar' cambió su ID en el DOM y el test
> de perfil ha roto. Mnemo lo recibe por webhook y lo triaja solo, sin que nadie mire el log."

### Qué se teclea

El bloque del push en vivo está preparado en `prod.local.md` (firma HMAC-SHA256 y `run_uid`
aleatorio para que cada ensayo ingeste un run fresco). En esencia:

```bash
# payload = fresh_push.json con org_id real y run_uid aleatorio
# firma  = HMAC-SHA256(cuerpo, CI_WEBHOOK_SECRET) en X-Hub-Signature-256
curl -X POST "$BACKEND_URL/v2/ci/webhook" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -d "$PAYLOAD"
```

### Qué se ve

1. El terminal devuelve el triaje en segundos: `"triage": {"maintenance": 1, ...}` — Mnemo
   clasifica el fallo de `test_perfil` como **mantenimiento** (el locator `#guardar` no existe;
   el DOM trae `#guardar-cambios`) y el acta sale **apto-con-reservas**: un fallo de
   mantenimiento no bloquea el release, lo deja señalado.
2. En el frontend, seleccionar el run recién llegado: triaje por test con evidencia
   (`TriageVerdictList`) y briefing ejecutivo (`BriefingCard`).
3. **El bloqueo rotundo**: seleccionar el run pre-sembrado con un **fallo real nuevo** →
   `GateCard` en rojo, acta **no-apto**. *"Cuando el fallo es real y nunca visto, Mnemo frena
   el release; cuando es mantenimiento o flaky, no te roba la mañana."*

### Mensaje clave

> "Triaje determinista en segundos, con la política de un QA senior: bloquear lo real,
> señalar lo demás. Nadie ha mirado un log."

---

## Acto 2 — La acción (self-heal + firma humana + acta verificable)

### Qué se dice

> "Mnemo no solo detecta: propone la solución — actualizar el locator de `#guardar` a
> `#guardar-cambios`. Pero la IA nunca firma sola: hace falta la aprobación de un ingeniero."

### Qué se hace en la UI

1. En **Acciones** (`ActionsPanel`) → clic en **"Proponer acciones"** → aparece la acción
   `self_heal` con el parche y la evidencia (el DOM contiene `id="guardar-cambios"`).
2. Clic en **"Aprobar"** → estado `approved`. *"Determinismo donde firmo, IA donde multiplico."*
3. Abrir **Certificado** (`CertificateCard`): veredicto firmado con **Ed25519**, con evidencia,
   desglose y `key_id`. Clic en **"Descargar PDF"**.
4. **El remate — verificación pública** (página `/verify`, sin login):
   - Pegar el acta (JSON canónico + firma) → **"válido"**.
   - Cambiar una sola letra del veredicto → **"inválido"**.

### Mensaje clave

> "Esto es un acta de aseguramiento, no un dashboard: cualquiera — un cliente, un auditor —
> puede verificarla criptográficamente sin tener cuenta en Mnemo. Como la cadena de suministro
> firma sus builds, nosotros firmamos el estado real de la calidad."

---

## Acto 3 — Aprendizaje + aislamiento (foso + Org B + ROI)

### Qué se dice

> "¿Y el run verde? Mnemo tampoco regala aptos: hasta que el motor no está calibrado con
> correcciones humanas, ni siquiera un run limpio recibe un apto rotundo. Esa honestidad es
> el producto."

### Qué se hace en la UI

1. **Re-run limpio** (pre-sembrado): acta verde **apto-con-reservas** — explicar el matiz:
   sin historial de calibración la confianza es baja y el sistema lo dice. *"El apto rotundo
   se gana con calibración, no se regala."*
2. **Calibración** (`/app/calibration`): etiquetar una familia (flaky/real/mantenimiento…) →
   las métricas del foso se actualizan. Cada corrección humana afina el siguiente triaje.
3. **Aislamiento multi-cliente**: cambiar en el topbar a **"Cliente Beta"** → sus runs no
   aparecen; los de Demo MTP tampoco al revés. RLS en vivo: cada cliente, su memoria.
4. **ROI** (`RoiPanel`): horas de triaje ahorradas, releases certificados, coste de API 0 €.

### Mensaje clave

> "El motor aprende de cada corrección — ese historial de calibración por cliente es el foso:
> no se puede clonar con un fork. Y cada cliente solo ve su memoria."

---

## Frase de cierre

> "Mnemo convierte el conocimiento de QA — que hoy se evapora con la rotación — en memoria
> permanente y en actas verificables. Determinista donde firma, asistido por IA donde escala,
> y con un coste marginal de cero. Gracias."

---

## Notas de presentación

- Hablar sobre la demo, no solo mostrarla: narrar el valor de cada transición.
- **Claim de privacidad, versión honesta**: la demo corre en la nube con un LLM gratuito
  (Gemini free tier vía endpoint compatible OpenAI). El pitch correcto es *"proveedor LLM
  configurable: 100% on-premise con Ollama para datos sensibles; esta demo usa la nube por
  accesibilidad"*. No decir "los datos nunca salen" mientras se enseña la demo cloud.
- Si el LLM no responde, el briefing degrada a texto determinista — mencionarlo como feature:
  el triaje, el acta y el gate no dependen del LLM.
- La firma de las actas es **Ed25519** (no ECDSA); el `key_id` dentro del acta permite rotar
  claves sin romper actas antiguas.
- El `gate` del webhook devuelve `null` si la organización no tiene la GitHub App conectada:
  degradación esperada, el semáforo del run en la UI no depende de ello.
- Plan B: ver `runbook.md` — los runs pre-sembrados cubren los tres actos sin push en vivo.
