# Desplegar Mnemo en producción

> **Estado actual:** el despliegue vigente de la demo corre en **Hugging Face Spaces**
> (gratis; ver `docs/demo/runbook.md`). Esta guía documenta **Render** como la ruta
> recomendada de pago (URL estable, sin sleep, auto-deploy); las variables son las mismas.

Mnemo son **dos piezas** que se despliegan por separado:

| Pieza | Qué es | Dónde va |
|-------|--------|----------|
| **Frontend** | Next.js | **Vercel** (ya lo tienes) |
| **Backend** | FastAPI (`Dockerfile` → `uvicorn asgi:app`) | un host que corra Docker/Python (esta guía) |
| **BD + Auth** | Postgres + GoTrue | **Supabase** (ya lo tienes; migraciones ya aplicadas) |

El frontend **no habla con la BD directamente**: cada `/api/v2/*` es un proxy server-side (`proxyToBackend`) que hace `fetch` a **`NEXT_PUBLIC_API_BASE_URL`**. Si esa variable falta o el backend no responde, **no carga nada** (500 "NEXT_PUBLIC_API_BASE_URL is not configured" o 502 "Could not reach backend API").

> **Por qué "no puedo crear una organización"**: crear org → `POST /api/v2/orgs` → proxy → backend. Sin backend desplegado + `NEXT_PUBLIC_API_BASE_URL` apuntándolo, falla. (No tiene nada que ver con el LLM.)

---

## Paso 1 — Backend en Render (recomendado)

Render despliega directamente desde el `Dockerfile` con HTTPS y URL estable.

1. **aistudio.google.com/apikey** → "Create API key" (gratis) → guárdala. *(El LLM: ver "Decisión de LLM" abajo.)*
2. En **render.com** → **New + → Blueprint** → conecta este repo. Render detecta `render.yaml`.
3. Rellena las variables marcadas `sync: false`:
   - `DATABASE_URL` = la cadena de conexión de tu Supabase (Project → Settings → Database → Connection string, **modo pooler/transaction**).
   - `SUPABASE_URL` = `https://<proyecto>.supabase.co`
   - `SUPABASE_JWKS_URL` = `https://<proyecto>.supabase.co/auth/v1/.well-known/jwks.json`
   - `OPENAI_API_KEY` = tu key de **Google AI Studio**
   - (`LLM_PROVIDER`, `OPENAI_BASE_URL`, `LLM_MODEL`, `ALLOW_EXTERNAL_LLM`, `SUPABASE_JWT_AUDIENCE` ya vienen con valor en `render.yaml` → apuntan a Gemini).
4. **Deploy**. Cuando esté verde, copia la URL pública: `https://mnemo-backend-XXXX.onrender.com`.
5. Comprueba el backend: abre `https://…onrender.com/v2/health` → debe responder OK.

> ⚠️ **RAM**: el embedder local (`sentence-transformers` → `torch`) usa ~1–1.5 GB. El plan **free/starter (512 MB) NO arranca** → `render.yaml` usa `plan: standard`. Si quieres 0 € estricto, ve a "Alternativas".

## Paso 2 — Conectar Vercel al backend

En **Vercel → tu proyecto → Settings → Environment Variables**:
- `NEXT_PUBLIC_API_BASE_URL` = la URL del backend del paso 1 (p.ej. `https://mnemo-backend-XXXX.onrender.com`) — **sin barra final**.
- Confirma también `NEXT_PUBLIC_SUPABASE_URL` y `NEXT_PUBLIC_SUPABASE_ANON_KEY` (para el login).
- Opcional: `NEXT_PUBLIC_GITHUB_APP_URL` = página de instalación de la GitHub App (`https://github.com/apps/<tu-app>/installations/new`) — activa el enlace "instalar ahora" en Integraciones.
- **Redeploy** el frontend (las `NEXT_PUBLIC_*` se hornean en build → hay que reconstruir).

Tras el redeploy: recarga, crea una organización → debe funcionar.

## Paso 3 — CORS (si hiciera falta)

El proxy de Next corre **server-side**, así que las llamadas al backend salen desde el servidor de Vercel (no del navegador) → normalmente **no hay problema de CORS**. Si en algún punto llamaras al backend directo desde el navegador, habría que añadir el dominio de Vercel a CORS en el backend.

---

## Decisión de LLM en producción

En local usabas **Ollama** (privado, 0 €). En prod no hay Ollama, así que:

- **Opción elegida — Google Gemini (gratis, externo)**: configurada en `render.yaml` vía el endpoint **compatible con OpenAI** de Gemini, así que el código no cambia (mismo `LLM_PROVIDER=openai`, solo cambia `OPENAI_BASE_URL`/`LLM_MODEL`). Clave gratis en `aistudio.google.com/apikey`. **Límites** del tier gratis (p.ej. `gemini-2.0-flash`): del orden de ~15 req/min y ~1.500 req/día — sobra para demo. **Privacidad**: envía datos del cliente a Google → por eso `ALLOW_EXTERNAL_LLM=true`. ⚠️ Choca con el mensaje "privado/on-premise": úsala para la **demo**, no como promesa de venta.
  - Config exacta: `LLM_PROVIDER=openai`, `ALLOW_EXTERNAL_LLM=true`, `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`, `LLM_MODEL=gemini-2.5-flash`, `OPENAI_API_KEY=<tu key de AI Studio>`.
  - **Elige bien el modelo:** `gemini-2.5-flash` (o `gemini-flash-latest`) tiene cuota gratis. `gemini-2.0-flash` puede devolver `429 "Quota exceeded ... limit: 0"` en algunas cuentas (ese modelo no tiene free tier ahí), y `gemini-1.5-flash` ya no existe (404). Si ves `429 limit: 0`, **cambia `LLM_MODEL`, no la clave.**
- **Groq (alternativa, también gratis y compatible OpenAI)**: `OPENAI_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=llama-3.3-70b-versatile`, `OPENAI_API_KEY=<key de console.groq.com>`.
- **Ollama propio (privado)**: una VM con `ollama serve` + `qwen3:8b`; en el backend `LLM_PROVIDER=ollama` + `OLLAMA_BASE_URL=http://<host-ollama>:11434`. Coherente con la narrativa on-premise; más coste/operación.
- **Sin IA (degradado)**: sin variables de LLM, las funciones de IA usan su plantilla/fallback (es justo lo que muestra "Plan no generado (LLM no accesible)"). La app carga y todo lo no-IA funciona.

Sea cual sea, **el backend arranca igual**: el LLM solo afecta a las funciones de IA, no a crear orgs / indexar / navegar.

---

## Claves de firma del acta (Ed25519) — sin esto el certificado está APAGADO

El diferenciador del producto (acta firmada y verificable) necesita **dos variables en el backend**. Si faltan, `GET /v2/certificates/pubkey` devuelve `503 "clave pública de firma no configurada"` y no se puede generar ni verificar ningún acta.

1. Genera el par (una sola vez, en tu máquina):
   ```bash
   openssl genpkey -algorithm ed25519 -out mnemo-signing-private.pem
   openssl pkey -in mnemo-signing-private.pem -pubout -out mnemo-signing-public.pem
   ```
2. En el host del backend (Render → Environment / HF Space → Settings):
   - `MNEMO_SIGNING_PRIVATE_KEY` = contenido completo de `mnemo-signing-private.pem` (**como Secret**, incluye las líneas `-----BEGIN/END PRIVATE KEY-----`).
   - `MNEMO_SIGNING_PUBLIC_KEY` = contenido completo de `mnemo-signing-public.pem` (puede ser Variable pública; es la clave publicable).
3. Comprueba: `GET https://<backend>/v2/certificates/pubkey` → `{"algorithm":"ed25519","public_key_pem":...}`.

> **Rotación**: cada acta lleva el `key_id` (SHA-256 truncado) de la clave con la que se firmó; los certificados antiguos siguen verificando con su clave. **No pierdas la privada** y no la reutilices en otros entornos.

---

## Webhook de CI (ingesta automática desde el CI del cliente)

Para que `POST /v2/ci/webhook` funcione (reporter de Playwright o cualquier emisor del
artefacto), el backend necesita **tres variables** (sin ellas responde 401/503):

| Variable | Qué es |
|----------|--------|
| `CI_WEBHOOK_SECRET` | Secreto compartido para la firma HMAC-SHA256 (`X-Hub-Signature-256`) |
| `CI_SERVICE_USER_ID` | UUID del usuario de servicio al que se atribuye la ingesta (debe ser miembro del org) |
| `CI_SERVICE_ORG_ID` | Opcional: si se define, el webhook rechaza (403) artefactos de cualquier otro org |

Relacionadas: `MNEMO_SECRET_KEY` (clave Fernet, **obligatoria si se usa la integración
Jira/Xray** — cifra las credenciales por-org) y las cotas anti-DoS `CI_MAX_BODY_BYTES`
e `INGEST_MAX_BYTES` (10 MiB por defecto; subidas/cuerpos mayores → 413). Todas
documentadas en `.env.example` y pre-declaradas en `render.yaml`.

---

## Keep-warm (hosting gratuito que se duerme)

Los hosts gratuitos (HF Spaces) duermen el backend por inactividad → la primera petición tarda ~60 s y el usuario ve un **504 al primer clic**. El workflow **`.github/workflows/keep-warm.yml`** pingea `GET /v2/health` cada 15 min y falla (→ email de aviso) si no responde 200.

Para activarlo: GitHub → Settings → Secrets and variables → Actions → **Variables** → `BACKEND_HEALTH_URL` = `https://<backend>/v2/health`. Sin la variable, el job se salta sin ruido.

---

## Alternativas de hosting del backend

| Host | 0 € real | RAM (torch) | Nota |
|------|----------|-------------|------|
| **Render** (esta guía) | No (plan standard) | ✅ ≥1 GB | el más directo; auto-deploy |
| **Fly.io** | casi | ✅ 1 GB configurable | `fly launch` detecta el Dockerfile; sin `$PORT` (usa 8080) |
| **Railway** | ~5 $/mes crédito | ✅ flexible | el más fácil; luego de pago |
| **Oracle Cloud Free** | ✅ siempre gratis | ✅ hasta 24 GB (VM ARM) | más setup (VM cruda) |
| **Hugging Face Spaces** (Docker) | ✅ | ✅ 16 GB | el Space es público y se duerme; requiere `app_port: 8080` en el frontmatter del README del Space (sin eso HF asume 7860) |

El `Dockerfile` ya es **portable**: escucha en `${PORT:-8080}`, así que sirve para todos (Render/Railway inyectan `$PORT`; Fly/Oracle/HF usan 8080).

> Ver también: `docs/demo/runbook.md` (operativa de la demo sobre este despliegue) y
> `docs/demo/guion.md` (guion de presentación).

---

## Checklist de verificación

- [ ] `GET https://<backend>/v2/health` responde OK.
- [ ] `NEXT_PUBLIC_API_BASE_URL` en Vercel apunta al backend (sin barra final) + redeploy hecho.
- [ ] En el sitio: la consola del navegador (Network) muestra `/api/v2/orgs` con **200** (no 500/502).
- [ ] Crear una organización funciona.
- [ ] Migraciones aplicadas en Supabase prod (ya lo están; verificable con `relrowsecurity` en `pg_class`).
- [ ] `GET https://<backend>/v2/certificates/pubkey` responde 200 con la clave pública (→ el acta firmada está operativa).
- [ ] Variable `BACKEND_HEALTH_URL` creada en GitHub → el workflow keep-warm corre verde cada 15 min.
