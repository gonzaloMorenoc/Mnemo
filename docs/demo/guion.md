# Guion de demo — Mnemo Autopilot (3 actos)

Demo de concurso MTP AI Innovation Award · versión: Bloque C (C4)

---

## Tabla de tiempos

| Acto | Contenido | Duración aprox. |
|------|-----------|-----------------|
| Apertura | Problema y propuesta | 30 s |
| Acto 1 | Push en vivo → gate rojo, triaje mantenimiento | 60 s |
| Acto 2 | Self-heal `#guardar`→`#guardar-cambios` + aprobación + cert/PDF/briefing | 75 s |
| Acto 3 | Re-run apto + calibración (foso) + Org B + ROI | 60 s |
| Cierre | Diferenciadores y call to action | 15 s |
| **Total** | | **~4 min** |

---

## Frase de apertura

> "Un cambio de botón en la UI rompe el test de perfiles — y el equipo de QA no sabe por qué.
> Mnemo lo detecta en automático, propone el parche exacto y, con una firma humana, cierra el ciclo.
> Sin datos que salgan al exterior, sin coste de API, con un certificado firmado en cada release."

---

## Acto 1 — El problema (push → gate rojo)

### Qué se dice

> "Aquí tenemos Org A 'Demo MTP', con los runs pre-cargados del sprint — flaky, infraestructura,
> real. Ahora llega el push del CI con el report de la suite checkout: el botón 'Guardar' cambió
> su ID en el DOM. Mnemo lo recibe vía webhook, lo triaja y levanta la barrera."

### Qué se teclea

```bash
# Terminal — enviar fresh_push.json al webhook con firma HMAC-SHA256
PAYLOAD=$(cat scripts/demo_fixtures/fresh_push.json)
SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$CI_WEBHOOK_SECRET" | awk '{print $2}')

curl -s -X POST http://localhost:8000/v2/ci/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -d "$PAYLOAD" | python3 -m json.tool
```

> Variables requeridas: `CI_WEBHOOK_SECRET` (mismo valor que en `.env`).
> El campo `org_id` en el payload debe coincidir con el `CI_SERVICE_ORG_ID` configurado.

### Qué se ve

1. El terminal imprime el JSON de respuesta con:
   - `"triage": {"category": "maintenance", ...}` — Mnemo clasifica automáticamente el fallo de `test_perfil` como **mantenimiento** (locator `#guardar` no existe; el DOM contiene `#guardar-cambios`).
   - `"verdict": "no-apto"` y `"gate": "failure"` — el release queda **bloqueado**.
2. En el frontend (`/app/autopilot`), al seleccionar el run recién ingresado:
   - **Briefing ejecutivo** (`BriefingCard`): "1 fallo de mantenimiento — locator obsoleto".
   - **Panel de triaje** (`TriageVerdictList`): fila `test_perfil` — categoría `mantenimiento`, confianza alta, evidencia: locator no encontrado + señal de contenido en DOM.
   - **Gate** (`GateCard`): semáforo rojo — **no-apto**.

### Mensaje clave

> "Un cambio de UI rompió el test. Mnemo lo detectó solo, sin intervención, y frenó el release
> automáticamente — determinismo donde importa."

---

## Acto 2 — La acción (self-heal + aprobación humana + cert/PDF/briefing)

### Qué se dice

> "Mnemo no solo detecta. Propone la solución: actualizar el locator de `#guardar` a `#guardar-cambios`.
> Pero la IA nunca firma sola — hace falta la aprobación de un ingeniero."

### Qué se teclea / qué se hace en la UI

1. En el panel **Acción Nivel 2** (`ActionsPanel`), el panel muestra "Sin acciones para este run." Hacer clic en el botón **"Proponer acciones"** (esquina superior derecha del panel → `POST /v2/actions/run/{run_id}/propose`).
   - Mientras se procesa, el botón muestra "Proponiendo…".
   - Al completarse aparece el toast **"Acciones propuestas."** y la acción `self_heal` aparece en la lista:
     - Tipo: `self_heal`
     - Parche: `locator #guardar → #guardar-cambios`
     - Evidencia: texto del DOM (`id="guardar-cambios"`) + diagnóstico del triaje.
2. El presentador hace clic en **"Aprobar"** (botón en la fila de la acción → `POST /v2/actions/{action_id}/approve`).
3. El estado pasa a `approved` / `materializing`.

4. Se hace clic en **"Certificado"** (`CertificateCard`):
   - Se muestra el veredicto firmado (ECDSA) con campos: `verdict`, `failures_known`, `failures_new`, `signed_at`.
   - Clic en **"Descargar PDF"** → `GET /v2/certificates/{run_id}/pdf` → se descarga el PDF.

5. El panel **Briefing ejecutivo** (`BriefingCard`) está visible con:
   - Narrativa LLM (o degradada si Ollama no responde): "Fallo de mantenimiento — locator `#guardar` obsoleto. Acción propuesta: actualizar a `#guardar-cambios`."

### Qué se ve

- Acción en estado `approved` con timestamp de aprobación.
- PDF descargado con el nombre del run y el sello `ECDSA-SHA256`.
- Briefing narrativo legible, generado localmente (sin datos al exterior).

### Mensaje clave

> "Determinismo donde firmo, IA donde multiplico. El parche lo propone el modelo local —
> los datos del cliente nunca salen — y un humano cierra el ciclo con su aprobación."

---

## Acto 3 — Aprendizaje + aislamiento (re-run apto + foso + Org B + ROI)

### Qué se dice

> "Imaginemos que el equipo actualiza el test, corre el CI de nuevo y el run entra verde.
> Mnemo emite el certificado 'apto' y actualiza sus métricas de calibración.
> Y ahora, la clave enterprise: el aislamiento multi-cliente."

### Qué se teclea / qué se hace en la UI

1. **Re-run limpio** (pre-sembrado como `perfil_green.json` en el seed):
   - Seleccionar en `RunSelector` el run de `test_perfil` con estado verde.
   - El `GateCard` muestra semáforo verde — **apto**.
   - `CertificateCard`: `verdict = "apto"`, descargable en PDF.

2. **Panel de calibración** (`/app/calibration`):
   - Tabla de métricas por categoría: `flaky`, `mantenimiento`, `infra`, `real` — precisión, cobertura, confianza media.
   - Cada corrección aprobada ajusta el umbral del siguiente triaje → el "foso" aprende.

3. **Selector de organización** (topbar, `OrgSwitcher`):
   - Clic en el selector → cambiar a **Org B "Cliente Beta"**.
   - La lista de runs muestra únicamente los de Org B — el run de `test_perfil` de Org A **no aparece**.
   - Demostración en vivo de la RLS (Row-Level Security): cada cliente solo ve su memoria.

4. **Panel ROI** (`RoiPanel`, en `/app/autopilot`):
   - Horas de triaje manual ahorradas (calculadas sobre los runs del sprint).
   - Coste de API: **0 €** (LLM y embeddings 100% locales).
   - Releases certificados: contador acumulado.

### Qué se ve

- Gate verde + PDF "apto".
- Tabla de calibración con métricas reales de los runs sembrados.
- Cambio de org en topbar → lista de runs vacía o diferente (Org B solo ve sus datos).
- Tarjeta ROI con cifras concretas del sprint demo.

### Mensaje clave

> "Cada cliente, su memoria. El motor aprende con cada corrección aprobada.
> Y para el evaluador de riesgos: coste de API cero, datos on-premise,
> certificado firmado en cada release — sin excusas para el CTO."

---

## Frase de cierre

> "Mnemo convierte el conocimiento de QA — que hoy se evapora con la rotación — en memoria
> permanente y accionable. Privado por diseño, determinista donde firma, asistido por IA donde escala.
> Gracias."

---

## Notas de presentación

- Hablar sobre la demo, no solo mostrarla: narrar en voz alta el valor de cada transición.
- Si el LLM (Ollama) no está activo, el briefing degrada a texto determinista — mencionarlo como feature, no como fallo: "privado por diseño, funciona aunque el modelo esté apagado".
- El PDF del certificado se puede mostrar en pantalla antes de descargarlo para que sea visible desde el proyector.
- Plan B: ver `runbook.md` — los datos pre-sembrados cubren los Actos 1 y 2 si el push en vivo falla.
