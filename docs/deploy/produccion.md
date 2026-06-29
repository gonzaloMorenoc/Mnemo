# Desplegar Mnemo en producción

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

1. **console.groq.com** → crea una API key (gratis) → guárdala. *(El LLM: ver "Decisión de LLM" abajo.)*
2. En **render.com** → **New + → Blueprint** → conecta este repo. Render detecta `render.yaml`.
3. Rellena las variables marcadas `sync: false`:
   - `DATABASE_URL` = la cadena de conexión de tu Supabase (Project → Settings → Database → Connection string, **modo pooler/transaction**).
   - `SUPABASE_URL` = `https://<proyecto>.supabase.co`
   - `SUPABASE_JWKS_URL` = `https://<proyecto>.supabase.co/auth/v1/.well-known/jwks.json`
   - `OPENAI_API_KEY` = tu key de Groq
   - (`LLM_PROVIDER`, `OPENAI_BASE_URL`, `LLM_MODEL`, `ALLOW_EXTERNAL_LLM`, `SUPABASE_JWT_AUDIENCE` ya vienen con valor en `render.yaml`).
4. **Deploy**. Cuando esté verde, copia la URL pública: `https://mnemo-backend-XXXX.onrender.com`.
5. Comprueba el backend: abre `https://…onrender.com/v2/health` → debe responder OK.

> ⚠️ **RAM**: el embedder local (`sentence-transformers` → `torch`) usa ~1–1.5 GB. El plan **free/starter (512 MB) NO arranca** → `render.yaml` usa `plan: standard`. Si quieres 0 € estricto, ve a "Alternativas".

## Paso 2 — Conectar Vercel al backend

En **Vercel → tu proyecto → Settings → Environment Variables**:
- `NEXT_PUBLIC_API_BASE_URL` = la URL del backend del paso 1 (p.ej. `https://mnemo-backend-XXXX.onrender.com`) — **sin barra final**.
- Confirma también `NEXT_PUBLIC_SUPABASE_URL` y `NEXT_PUBLIC_SUPABASE_ANON_KEY` (para el login).
- **Redeploy** el frontend (las `NEXT_PUBLIC_*` se hornean en build → hay que reconstruir).

Tras el redeploy: recarga, crea una organización → debe funcionar.

## Paso 3 — CORS (si hiciera falta)

El proxy de Next corre **server-side**, así que las llamadas al backend salen desde el servidor de Vercel (no del navegador) → normalmente **no hay problema de CORS**. Si en algún punto llamaras al backend directo desde el navegador, habría que añadir el dominio de Vercel a CORS en el backend.

---

## Opción recomendada sin tarjeta — Hugging Face Spaces (0 €, 16 GB)

HF Spaces da 16 GB de RAM en el tier gratuito de CPU **sin pedir tarjeta**, y corre tu `Dockerfile`. Plantilla lista en `deploy/hf-spaces/` (Dockerfile + README): el Space solo necesita **esos 2 ficheros** — el backend se **clona del repo público en build** (no duplicas código) y el modelo de embeddings se **pre-descarga en build** (el disco del Space es efímero).

1. **huggingface.co/new-space** → SDK **Docker** → Space **público** (el free es público; tu repo ya lo es).
2. En el repo del Space, sube **`deploy/hf-spaces/Dockerfile`** y **`deploy/hf-spaces/README.md`** a la **raíz** (renómbralos a `Dockerfile` y `README.md`). El más fácil: clona el repo del Space (`git clone https://huggingface.co/spaces/<user>/<space>`), copia los 2 ficheros, `git add . && git commit && git push`.
3. **Settings → Variables and secrets**: añade los **secrets** (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_JWKS_URL`, `OPENAI_API_KEY`) y las **variables** (`SUPABASE_JWT_AUDIENCE`, `LLM_PROVIDER`, `ALLOW_EXTERNAL_LLM`, `OPENAI_BASE_URL`, `LLM_MODEL`). En HF se inyectan como env vars en runtime (los lee `os.getenv`).
4. El Space buildea solo (clona → instala → pre-descarga el modelo → arranca). Mira los **logs** del build.
5. URL pública: `https://<usuario>-<space>.hf.space` → verifica `…/v2/health`.
6. **Vercel** → `NEXT_PUBLIC_API_BASE_URL` = esa URL (sin barra final) → **Redeploy**.

Notas HF: el Space corre como **UID 1000** (ya contemplado en el Dockerfile), **se duerme** con inactividad (cold start al volver) y para **actualizar el backend** se hace *Factory rebuild* (re-clona el repo). Es la mejor opción 0 €-con-RAM; para algo siempre-encendido, un PaaS de pago o una VM.

## Decisión de LLM en producción

En local usabas **Ollama** (privado, 0 €). En prod no hay Ollama, así que:

- **Opción elegida — Groq (gratis, externo)**: ya configurada en `render.yaml`. Rápida, sin GPU. **Límites**: rate limits del tier gratis (sobra para demo; corto para carga real). **Privacidad**: envía los datos del cliente a Groq → por eso `ALLOW_EXTERNAL_LLM=true`. ⚠️ Choca con el mensaje "privado/on-premise" de Mnemo: úsala para la **demo**, no como promesa de venta.
- **Ollama propio (privado)**: una VM con `ollama serve` + `qwen3:8b`; en el backend `LLM_PROVIDER=ollama` + `OLLAMA_BASE_URL=http://<host-ollama>:11434`. Coherente con la narrativa on-premise; más coste/operación.
- **Sin IA (degradado)**: sin variables de LLM, las funciones de IA usan su plantilla/fallback. La app carga y todo lo no-IA funciona.

Sea cual sea, **el backend arranca igual**: el LLM solo afecta a las funciones de IA, no a crear orgs / indexar / navegar.

---

## Alternativas de hosting del backend

| Host | 0 € real | RAM (torch) | Nota |
|------|----------|-------------|------|
| **Render** (esta guía) | No (plan standard) | ✅ ≥1 GB | el más directo; auto-deploy |
| **Fly.io** | casi | ✅ 1 GB configurable | `fly launch` detecta el Dockerfile; sin `$PORT` (usa 8080) |
| **Railway** | ~5 $/mes crédito | ✅ flexible | el más fácil; luego de pago |
| **Oracle Cloud Free** | ✅ siempre gratis | ✅ hasta 24 GB (VM ARM) | más setup (VM cruda) |
| **Hugging Face Spaces** (Docker) | ✅ | ✅ 16 GB | el Space es público y se duerme |

El `Dockerfile` ya es **portable**: escucha en `${PORT:-8080}`, así que sirve para todos (Render/Railway inyectan `$PORT`; Fly/Oracle/HF usan 8080).

---

## Checklist de verificación

- [ ] `GET https://<backend>/v2/health` responde OK.
- [ ] `NEXT_PUBLIC_API_BASE_URL` en Vercel apunta al backend (sin barra final) + redeploy hecho.
- [ ] En el sitio: la consola del navegador (Network) muestra `/api/v2/orgs` con **200** (no 500/502).
- [ ] Crear una organización funciona.
- [ ] Migraciones aplicadas en Supabase prod (ya lo están; verificable con `relrowsecurity` en `pg_class`).
