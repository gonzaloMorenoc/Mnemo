# Runbook de demo — Mnemo

Cómo dejar la demo lista y el plan B. La demo se hace contra **producción** (sección 1);
el entorno local queda como alternativa de desarrollo (sección 2).

Los **valores concretos** del despliegue (URLs con UUIDs, secreto del webhook, run_ids
sembrados) viven en `prod.local.md` — un archivo **local, ignorado por git**: este runbook es
público y no debe contener identificadores del entorno real.

---

## 1. Demo contra producción (recomendado)

### 1a. Arquitectura del despliegue

| Pieza | Dónde | Notas |
|-------|-------|-------|
| Frontend (Next.js) | Vercel | habla con el backend vía proxy server-side (`NEXT_PUBLIC_API_BASE_URL`) |
| Backend (FastAPI) | contenedor en la nube (HF Space) | keep-warm por GitHub Action cada 15 min |
| BD + Auth | Supabase | RLS multi-tenant |
| LLM | Gemini free tier (configurable: Groq / Ollama on-premise) | las funciones no-LLM no dependen de él |

### 1b. Estado pre-sembrado

El seed (`src/demo/seed.py`) ya está aplicado en producción:

- **Org A "Demo MTP"** — 5 runs procesados (ingesta → triaje → acta firmada Ed25519):
  mantenimiento verde→rojo, flaky, **real (no-apto)** y re-run verde.
- **Org B "Cliente Beta"** — 1 run propio (demostración de aislamiento RLS).
- **Escenario María→Pablo** (`src/demo/seed_continuity.py`, idempotente por título): el
  oficio de `checkout-suite` (runbooks, datos de prueba, contactos, decisiones, lección
  del PSP) + la riqueza semanal (`seed_riqueza.py`) que deja el arco del índice:
  `checkout-suite`=95 frente a `banca-movil`=25.
- Actas firmadas con la clave de producción → verifican en la página pública `/verify`.

Para re-sembrar desde cero: borrar las dos orgs (SQL en §1f) y ejecutar el seed **con
`MNEMO_SIGNING_PRIVATE_KEY`/`_PUBLIC_KEY` de producción en el entorno** — si faltan, las
actas salen sin firmar y el momento `/verify` de la demo no funciona:

```bash
python3 -c "
import os
from src.demo.seed import seed_demo
print(seed_demo(db_url=os.environ['DATABASE_URL'], demo_user_id='<TU_USER_UUID>'))"
```

### 1c. El push en vivo (opcional, Acto 4)

`scripts/demo_fixtures/fresh_push.json` es la munición: el run de `test_perfil` con el error
`locator not found: #guardar` (el DOM ya trae `#guardar-cambios`). El webhook exige firma
HMAC-SHA256 del cuerpo en `X-Hub-Signature-256` (estilo GitHub webhooks).

Reglas del comando (versión ejecutable con valores reales: `prod.local.md`):

- `org_id` del payload = UUID de Org A (el webhook rechaza otras orgs).
- **`run_uid` aleatorio en cada envío, con prefijo `demo-`** (p.ej. `demo-$(uuidgen)`) →
  cada ensayo ingesta un run fresco (la ingesta es idempotente por `run_uid`: reenviar el
  mismo valor devuelve `deduplicated: true`), y la poda de §1f (`like 'demo-%'`) los captura.
- Secreto: `CI_WEBHOOK_SECRET` configurado como secret del backend.

Respuesta esperada: `"triage": {"maintenance": 1}`, acta `apto-con-reservas`,
`"gate": null` si la org no tiene GitHub App conectada (esperado).

### 1c-bis. Los dos enlaces de verificación (Acto 2)

Vale igual para el **acta de traspaso** (vista Continuidad → «Copiar enlace de
verificación») que para el acta de un run: los dos enlaces llevan el mismo formato
`/verify#v1.<blob>`. Para el traspaso, el retoque creíble es subir `continuity.score`.

El enlace auténtico se obtiene desde la tarjeta del acta → **"Copiar enlace de
verificación"**; se abre en cualquier ventana sin sesión (incógnito, o el móvil) y se
verifica solo, sin tocar nada más.

El contraste es lo que convence — el verde solo se cree cuando antes se ha visto el
rojo —, así que conviene preparar con antelación un **segundo enlace, manipulado**:

1. Copiar el enlace auténtico y decodificar el fragmento tras `#v1.` (base64url) para
   recuperar el JSON del acta.
2. Editar el contenido — p.ej. bajar el `risk_score` — y volver a codificar el JSON
   completo en base64url, dejando la **firma original intacta**.
3. Montar la URL con ese fragmento nuevo: `/verify#v1.<blob manipulado>`.

**Ojo, es contraintuitivo:** cambiar un carácter suelto del base64 a mano NO sirve —
corrompe el JSON entero y el enlace cae en el aviso neutro "este enlace está
incompleto" (`decodeShare` ni siquiera consigue parsearlo), no en el rojo de "Firma NO
válida". El rojo solo aparece cuando el JSON decodifica bien pero la firma ya no
cuadra con el contenido — que es además la historia que se cuenta: "alguien retoca el
acta para que parezca mejor".

### 1d. Requisitos del backend en producción

Secrets/variables que deben existir en el host del backend (ver `docs/deploy/produccion.md`):

| Variable | Para qué |
|----------|----------|
| `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWKS_URL`, `SUPABASE_JWT_AUDIENCE` | BD y auth |
| `MNEMO_SIGNING_PRIVATE_KEY` / `MNEMO_SIGNING_PUBLIC_KEY` | firma Ed25519 de las actas |
| `CI_WEBHOOK_SECRET`, `CI_SERVICE_USER_ID`, `CI_SERVICE_ORG_ID` | push en vivo (opcional, Acto 4) |
| `LLM_PROVIDER`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, `ALLOW_EXTERNAL_LLM` | LLM (opcional: sin él, degradación elegante) |

### 1e. Checklist 30 minutos antes

- [ ] `GET <backend>/v2/health` → 200 (keep-warm activo; si tarda, abrirlo y esperar).
- [ ] `GET <backend>/v2/certificates/pubkey` → 200 (la firma está encendida).
- [ ] `/v2/health` → `llm.configured: true` (el Acto 3 lo usa; sin él degrada a fuentes).
- [ ] Login en el frontend: el selector muestra **solo** las orgs de demo (retirar
      cualquier org de pruebas de la cuenta antes del día).
- [ ] **Acto 1**: `/app/continuity?project=checkout-suite` = 95 y `banca-movil` = 25 (si no, ver la
      riqueza en §1f: `arc_ok`).
- [ ] **Acto 2**: «Emitir acta de traspaso» de `checkout-suite` ensayado la víspera (queda
      como `handover/latest` para el plan B) y sus dos enlaces probados en una ventana sin
      sesión: auténtico → sello; manipulado → «Firma NO válida».
- [ ] **Acto 3**: las tres preguntas del guion lanzadas en la app; leer las respuestas
      (el LLM no es determinista: si alguna se tuerce, ajustar la pregunta, no el guion).
- [ ] **Acto 4**: el dashboard tiene runs de la semana (riqueza re-ejecutada, §1f) y un
      run **con fallos** (p. ej. de `tienda-online`) se abre desde «Runs recientes» con sus
      veredictos y su acta.
- [ ] (Opcional) terminal con el push en vivo preparado (`prod.local.md`). **Hacerlo después
      del Acto 2**: `fresh_push.json` mete un fallo en `checkout-suite` y puede mover su
      índice. Si se ensaya antes, comprobar de nuevo el 95.
- [ ] Runs de ensayos anteriores podados (§1f) si se quiere la org limpia.

### 1f. Mantenimiento de los datos de demo

```sql
-- Podar los runs de ensayo del push en vivo (conserva los sembrados)
delete from public.test_runs
 where org_id = '<ORG_A_UUID>' and run_uid like 'demo-%';

-- Reset TOTAL (borra las dos orgs; después, re-seed según §1b)
delete from public.organizations
 where name in ('Demo MTP','Cliente Beta') and created_by = '<TU_USER_UUID>';
```

- **La semana de la demo**: re-ejecutar la riqueza para que la org llegue viva —
  `PYTHONPATH=. python3 -c "import os; from src.demo.seed_riqueza import seed_riqueza; print(seed_riqueza(db_url=os.environ['DATABASE_URL'], demo_user_id='<TU_USER_UUID>'))"`.
  Es idempotente por semana (`run_uid` `riqueza-…`, a salvo de la poda de arriba, que
  solo toca `demo-%`): añade solo las semanas que falten desde la última vez, y termina
  verificando el arco del índice (Actos 1-2) — el resultado debe incluir `arc_ok: True`
  (checkout-suite=95 y banca-movil=25).
- **Actas de los runs semanales**: la riqueza también emite el acta (triaje del motor
  + veredicto firmado) de cada run de la org que no la tenga — sin ella el dashboard
  muestra «sin veredicto aún». Requiere `MNEMO_SIGNING_PRIVATE_KEY`/`_PUBLIC_KEY` de
  **producción** en el entorno (como §1b; desde la rotación del 14-ago el `.env` del
  checkout de trabajo la lleva — comprobar que su `key_id` coincide con el de
  `/v2/certificates/pubkey`): sin clave el resultado sale `actas: 0` y los runs quedan
  sin veredicto; con una clave distinta las actas NO verificarían en `/verify`.

### 1g. Plan B

| Si falla… | Se enseña |
|---|---|
| Emitir el acta de traspaso (Acto 2) | la última emitida en el ensayo (la vista la recupera de `handover/latest`) y su enlace |
| El LLM (Acto 3) | la respuesta degradada: «LLM no accesible. Fuentes relevantes: …» — y decirlo como virtud |
| El push en vivo (Acto 4, opcional) | cualquier run sembrado: `maintenance_red` (recién llegado del CI) o `real` (no-apto) |

El acta de un run (Acciones → Aprobar → Certificado → `/verify`) sigue disponible sobre
cualquier run sembrado para preguntas del jurado.

---

## 2. Alternativa: entorno local (desarrollo)

<details>
<summary>Desplegar la demo en localhost (solo para desarrollo)</summary>

1. **Backend**: `pip install -r requirements.txt && uvicorn asgi:app --port 8000`
   con `.env` completo (mismas variables de §1d; para LLM local: `ollama pull qwen3:8b`
   y `LLM_PROVIDER=ollama`).
2. **Frontend**: `cd frontend && npm install && npm run dev` con `frontend/.env.local`
   (`NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` + claves de Supabase).
3. **Seed + usuario demo**: `python3 scripts/docker_init.py` — espera BD, aplica las
   migraciones, crea el usuario vía GoTrue y ejecuta `seed_demo`. Lee el `.env` de la raíz;
   necesita 5 variables: `DATABASE_URL`, `SUPABASE_URL`, `SERVICE_ROLE_KEY`, `DEMO_EMAIL`
   y `DEMO_PASSWORD`.
4. El push en vivo es idéntico a §1c apuntando a `http://localhost:8000`.

</details>
