# Runbook de ensayo — Mnemo Autopilot Demo

Instrucciones para dejar la demo lista y el plan B.

---

## 1. Pre-requisitos

### Variables de entorno (`.env` o entorno del sistema)

| Variable | Descripción | Obligatoria |
|----------|-------------|-------------|
| `DATABASE_URL` | Cadena de conexión Postgres — usar el **Session pooler** de Supabase (no la URL directa IPv6-only). Ejemplo: `postgresql://postgres.xxx:password@aws-0-eu-west-1.pooler.supabase.com:5432/postgres` | Sí |
| `SUPABASE_URL` | URL del proyecto Supabase (`https://xxx.supabase.co`) | Sí |
| `SUPABASE_JWKS_URL` | URL de las claves públicas JWT (`https://xxx.supabase.co/auth/v1/.well-known/jwks.json`) | Sí |
| `SUPABASE_JWT_SECRET` | Secreto JWT del proyecto (alternativa a JWKS para verificación local) | Cond. |
| `SERVICE_ROLE_KEY` | Clave service-role de Supabase (para que `docker_init.py` cree el usuario demo vía GoTrue) | Solo para init |
| `DEMO_EMAIL` | Email del usuario demo (ej. `demo@mnemo.local`) | Solo para init |
| `DEMO_PASSWORD` | Contraseña del usuario demo | Solo para init |
| `CI_WEBHOOK_SECRET` | Secreto compartido HMAC-SHA256 del webhook (`POST /v2/ci/webhook`). El push en vivo usa este valor para firmar. | Sí |
| `CI_SERVICE_USER_ID` | UUID del usuario de servicio que recibirá los runs del webhook (el mismo `demo_user_id`) | Sí |
| `CI_SERVICE_ORG_ID` | UUID de Org A "Demo MTP" (se obtiene tras correr el seed). El webhook rechaza runs de otras orgs. | Sí |
| `MNEMO_SIGNING_PRIVATE_KEY` | Clave privada ECDSA en PEM para firmar certificados | Para certs firmados |
| `MNEMO_SIGNING_PUBLIC_KEY` | Clave pública ECDSA en PEM para verificar certificados | Para certs firmados |
| `ALLOW_EXTERNAL_LLM` | `false` (por defecto). Poner `true` solo si se quiere usar un proveedor LLM externo — **enviará datos fuera**. En demo dejar `false`. | No (defecto OK) |

### Modelos locales (Ollama)

```bash
ollama pull deepseek-r1:8b
ollama serve   # si no está corriendo como servicio
```

Si Ollama no está disponible, el sistema **degrada con elegancia**: el briefing narrativo omite la parte LLM y muestra el veredicto determinista. Mencionarlo como feature durante la demo.

---

## 2. Levantar el entorno

### 2a. Backend (FastAPI)

```bash
# Desde la raíz del repo
pip install -r requirements.txt

uvicorn asgi:app --host 0.0.0.0 --port 8000 --reload
```

El backend queda en `http://localhost:8000`. Verificar salud:

```bash
curl http://localhost:8000/v2/health
```

### 2b. Frontend (Next.js)

```bash
cd frontend
npm install

# Desarrollo (HMR activo, recomendado para demo)
npm run dev
# → http://localhost:3000

# O producción
npm run build && npm start
```

Variables de entorno del frontend (fichero `frontend/.env.local`):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
```

Ver `frontend/.env.example` para la lista completa.

### 2c. Correr el seed (Org A + Org B)

El seed es idempotente — se puede re-ejecutar sin duplicar datos.

**Opción A — directo (sin Docker):**

```bash
# Asegurarse de que DATABASE_URL, SUPABASE_URL, SERVICE_ROLE_KEY,
# DEMO_EMAIL y DEMO_PASSWORD están en el entorno.

python3 scripts/docker_init.py
```

`docker_init.py` ejecuta en orden: espera a la BD, aplica las migraciones (`db/migrations/*.sql`), crea el usuario demo vía la admin API de GoTrue de Supabase y llama a `src.demo.seed.seed_demo`.

**Opción B — Docker Compose (si existe un `docker-compose.yml` local):**

El servicio `init` del compose llama a `docker_init.py` automáticamente al arrancar.

**Resultado esperado del seed:**

```
migración aplicada: db/migrations/001_*.sql
...
demo sembrada: {
  "org_a": "<UUID-Org-A>",
  "org_b": "<UUID-Org-B>",
  "runs": [
    {"fixture": "maintenance_green.json", "run_id": "..."},
    {"fixture": "maintenance_red.json",   "run_id": "..."},
    {"fixture": "flaky.json",             "run_id": "..."},
    {"fixture": "real.json",              "run_id": "..."},
    {"fixture": "perfil_green.json",      "run_id": "..."}
  ],
  "fresh_artifact_path": "scripts/demo_fixtures/fresh_push.json"
}
```

Anotar el `org_a` UUID — se necesita para `CI_SERVICE_ORG_ID`.

---

## 3. El push en vivo (Acto 1)

`scripts/demo_fixtures/fresh_push.json` contiene el run de `test_perfil` con el error `locator not found: #guardar` (el DOM ya tiene `#guardar-cambios`). Este payload **no** se ingesta durante el seed; es la munición del Acto 1.

Antes de enviarlo, actualizar el campo `org_id` del JSON para que coincida con el UUID de Org A:

```bash
# Sustituir __ORG__ por el UUID real de Org A
sed -i '' "s/__ORG__/$CI_SERVICE_ORG_ID/g" scripts/demo_fixtures/fresh_push.json
```

> Nota: `fresh_push.json` ya viene con `"org_id": "__ORG__"` como placeholder.
> Si ya fue editado en una ejecución anterior, verificar que el valor es correcto.

### Comando de push en vivo

El webhook espera la firma HMAC-SHA256 en la cabecera `X-Hub-Signature-256: sha256=<hex>`,
calculada sobre el cuerpo raw (idéntico al estilo de GitHub webhooks).

```bash
# Asegurarse de que CI_WEBHOOK_SECRET está en el entorno
PAYLOAD=$(cat scripts/demo_fixtures/fresh_push.json)

# Calcular la firma con openssl
SIG=$(printf '%s' "$PAYLOAD" | openssl dgst -sha256 -hmac "$CI_WEBHOOK_SECRET" | awk '{print $2}')

# Enviar al webhook
curl -s -X POST http://localhost:8000/v2/ci/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -d "$PAYLOAD" | python3 -m json.tool
```

**Respuesta esperada (éxito):**

```json
{
  "run_id": "<UUID del run ingresado>",
  "deduplicated": false,
  "triage": {
    "category": "maintenance",
    "confidence": 0.9,
    ...
  },
  "verdict": "no-apto",
  "gate": "failure"
}
```

Apuntar el `run_id` para seleccionarlo en el `RunSelector` del frontend.

---

## 4. Checklist pre-demo

Ejecutar este checklist **30 minutos antes** de la presentación:

- [ ] Backend arrancado: `curl http://localhost:8000/v2/health` responde `200 OK`.
- [ ] Frontend arrancado: `http://localhost:3000` carga sin errores de consola.
- [ ] Seed aplicado: Org A "Demo MTP" existe con 5 runs pre-sembrados.
- [ ] Org B "Cliente Beta" existe con 1 run.
- [ ] Login funciona con `DEMO_EMAIL` / `DEMO_PASSWORD`.
- [ ] El selector de organización (topbar) muestra al menos 2 orgs.
- [ ] Seleccionar el run `maintenance_red` de Org A → gate rojo visible (`GateCard`).
- [ ] Descargar el PDF del certificado de ese run → se descarga sin error (verificar que `MNEMO_SIGNING_PRIVATE_KEY` está configurada; si no, el certificado degrada a "sin firma").
- [ ] Ir a `/app/calibration` → la tabla de métricas carga (aunque sea con ceros si no hay datos de calibración previos).
- [ ] `fresh_push.json` tiene el `org_id` actualizado con el UUID de Org A.
- [ ] `CI_SERVICE_ORG_ID` en el entorno coincide con ese UUID.
- [ ] Ollama corriendo (opcional pero recomendado): `ollama list` muestra `deepseek-r1:8b`.
- [ ] Terminal con el comando curl del push en vivo preparado y listo para ejecutar.

---

## 5. Plan B (si el push en vivo falla)

Si el comando curl falla (red, firma incorrecta, backend reiniciado), los datos **pre-sembrados**
del seed cubren el mismo discurso:

| Fixture pre-sembrado | Equivale a |
|----------------------|------------|
| `maintenance_red.json` | El run "roto" del Acto 1 — triaje `mantenimiento`, gate rojo |
| `maintenance_green.json` | El run "verde previo" — contexto del cambio |
| `perfil_green.json` | El re-run apto del Acto 3 |

**Guion adaptado para Plan B:**

- **Acto 1:** seleccionar directamente el run `maintenance_red` pre-sembrado. Decir: "Este es el run que acaba de llegar del CI — ya triado en tiempo real". El gate rojo y el triaje de mantenimiento están ahí; solo se omite el curl en vivo.
- **Acto 2:** el run pre-sembrado ya tiene acciones propuestas si el seed corrió correctamente con el self-heal activado. Si no, describir el flujo verbalmente y mostrar el certificado pre-generado.
- **Acto 3:** no depende del push en vivo — el re-run apto (`perfil_green.json`), la calibración y el cambio de org son independientes.

El Acto 3 (calibración + Org B + ROI) **no depende del push en vivo** en ningún escenario.

---

## 6. Atajos útiles durante la demo

```bash
# Ver los UUIDs de las orgs del usuario demo
psql "$DATABASE_URL" -c "SELECT id, name FROM public.organizations WHERE created_by='<DEMO_USER_ID>';"

# Ver los runs de Org A
psql "$DATABASE_URL" -c "SELECT id, project, created_at FROM public.ci_runs WHERE org_id='<ORG_A_ID>' ORDER BY created_at DESC LIMIT 10;"

# Resetear el seed (eliminar Org A y Org B para empezar de cero)
psql "$DATABASE_URL" -c "DELETE FROM public.organizations WHERE name IN ('Demo MTP','Cliente Beta') AND created_by='<DEMO_USER_ID>';"
# Luego volver a correr: python3 scripts/docker_init.py
```
