# Desplegar Mnemo en producción

La demo pública corre en **Hugging Face Spaces** (plan gratuito). Esta guía documenta
además **Render**, la opción de pago más directa (URL estable, sin suspensión por
inactividad, despliegue automático); las variables son las mismas en cualquier host.

Mnemo son **tres piezas** que se despliegan por separado:

| Pieza | Qué es | Dónde va |
|-------|--------|----------|
| **Frontend** | Next.js | **Vercel** |
| **Backend** | FastAPI (`Dockerfile` → `uvicorn asgi:app`) | un host que ejecute contenedores Docker (esta guía) |
| **BD + Auth** | Postgres con pgvector + Supabase Auth | **Supabase** |

El frontend **no habla con la BD directamente**: cada `/api/v2/*` es un proxy de servidor
(`proxyToBackend`) que reenvía a **`NEXT_PUBLIC_API_BASE_URL`**. Si esa variable falta o
el backend no responde, la app no carga datos (500 «NEXT_PUBLIC_API_BASE_URL is not
configured» o 502 «Could not reach backend API»). Por ejemplo, crear una organización
(`POST /api/v2/orgs`) falla si el backend no está desplegado o la variable no lo apunta;
no tiene que ver con el LLM.

---

## Paso 1 — Base de datos en Supabase

1. Crea el proyecto en Supabase y copia la cadena de conexión del **Session pooler**
   (Project → Settings → Database → Connection string → *Session pooler*, puerto 5432).
   La conexión directa `db.<ref>.supabase.co` es solo IPv6 en proyectos nuevos y puede
   no enrutar desde el host del backend.
2. Aplica **todas las migraciones de `db/migrations/`, en orden**, antes de desplegar el
   backend: el código asume el esquema ya migrado.

   ```bash
   for f in db/migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
   ```

   Son idempotentes (`if exists` / `if not exists`), así que volver a aplicarlas no rompe
   nada; `scripts/docker_init.py` las re-aplica en cada arranque del entorno Docker. Cuando
   haya migraciones nuevas, se aplican antes de desplegar el backend que las necesita.

## Paso 2 — Backend en Render

Render despliega directamente desde el `Dockerfile` con HTTPS y URL estable.

1. En **render.com** → **New + → Blueprint** → conecta el repositorio. Render detecta
   `render.yaml`.
2. Rellena las variables marcadas `sync: false`:
   - `DATABASE_URL` = la cadena del **Session pooler** del paso 1.
   - `SUPABASE_URL` = `https://<proyecto>.supabase.co`
   - `SUPABASE_JWKS_URL` = `https://<proyecto>.supabase.co/auth/v1/.well-known/jwks.json`
   - `OPENAI_API_KEY` = la clave del proveedor de LLM (ver «LLM en producción»).
   - Las claves de firma, el webhook de CI y `MNEMO_SECRET_KEY` (secciones siguientes).
   - `LLM_PROVIDER`, `OPENAI_BASE_URL`, `LLM_MODEL`, `ALLOW_EXTERNAL_LLM` y
     `SUPABASE_JWT_AUDIENCE` ya vienen con valor en `render.yaml` (Groq con
     `openai/gpt-oss-120b`).
3. **Deploy**. Cuando esté en verde, copia la URL pública:
   `https://mnemo-backend-XXXX.onrender.com`.
4. Comprueba el backend: `https://…onrender.com/v2/health` debe responder 200.

> **RAM:** el embedder local (`sentence-transformers` → `torch`) usa entre 1 y 1,5 GB. El
> plan free/starter de Render (512 MB) no arranca; por eso `render.yaml` usa
> `plan: standard`. Para un coste cero, ver «Alternativas».

## Paso 3 — Conectar Vercel al backend

En **Vercel → proyecto → Settings → Environment Variables**:

- `NEXT_PUBLIC_API_BASE_URL` = la URL del backend (p. ej.
  `https://mnemo-backend-XXXX.onrender.com`), **sin barra final**.
- `NEXT_PUBLIC_SUPABASE_URL` y `NEXT_PUBLIC_SUPABASE_ANON_KEY` (para el login).
- Opcional: `NEXT_PUBLIC_GITHUB_APP_URL` = página de instalación de la GitHub App
  (`https://github.com/apps/<tu-app>/installations/new`); activa el enlace «instalar
  ahora» en Integraciones.
- Root Directory = `frontend`; Node 22.x (`frontend/.nvmrc`).

Las `NEXT_PUBLIC_*` se fijan en el build: tras cambiarlas hay que volver a desplegar el
frontend. Después, crear una organización desde la app debe funcionar.

**CORS:** el proxy de Next se ejecuta en el servidor, así que las llamadas al backend
salen de Vercel y no del navegador; normalmente no hace falta configurar CORS.

---

## Cambio del modelo de embeddings

El modelo por defecto es **multilingüe** (`paraphrase-multilingual-MiniLM-L12-v2`, 384
dimensiones, las mismas columnas `vector(384)`). Si se cambia `EMBEDDING_MODEL` (o se
viene de un despliegue con el modelo inglés `all-MiniLM-L6-v2`), hay que **re-embeber los
vectores existentes justo después de desplegar**: los espacios vectoriales de dos modelos
no son comparables y, hasta re-embeber, la búsqueda semántica y el agrupado de familias
dan resultados vacíos o sin sentido.

```bash
DATABASE_URL=... python3 -m scripts.reembed --dry-run   # cuenta filas, no escribe
DATABASE_URL=... python3 -m scripts.reembed             # regenera todo (idempotente)
```

Cubre `failures`, los centroides de `defect_families`, `qa_knowledge`, `test_assets` y la
razón de las etiquetas (`triage_corrections.reason_embedding`).

---

## LLM en producción

Sin `LLM_PROVIDER` no hay LLM y las funciones de IA degradan a su vía determinista. El
backend arranca igual: el LLM solo afecta a las funciones de IA, no a crear
organizaciones, ingerir runs, firmar actas ni navegar.

- **Groq con `openai/gpt-oss-120b`** (es el de la demo y el que trae `render.yaml`):
  `LLM_PROVIDER=openai`, `ALLOW_EXTERNAL_LLM=true`,
  `OPENAI_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=openai/gpt-oss-120b`,
  `OPENAI_API_KEY=<clave de console.groq.com/keys>`. Es un modelo que razona antes de
  responder; `generate_structured` le exige JSON en el prompt para que la salida sea
  utilizable.
- **Google Gemini** (alternativa, con capa gratuita): mismo `LLM_PROVIDER=openai` a través
  del endpoint compatible con OpenAI de Gemini.
  `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`,
  `LLM_MODEL=gemini-2.5-flash`, `OPENAI_API_KEY=<clave de aistudio.google.com/apikey>`.
  Si aparece `429 "Quota exceeded ... limit: 0"`, ese modelo no tiene capa gratuita en la
  cuenta: cambia `LLM_MODEL`, no la clave.
- **Ollama propio**: una máquina con `ollama serve` y un modelo descargado; en el backend,
  `LLM_PROVIDER=ollama` y `OLLAMA_BASE_URL=http://<host-ollama>:11434`. Los datos no salen
  de la infraestructura propia, a cambio de más coste de operación.
- **Sin IA**: sin variables de LLM, las funciones de IA devuelven su plantilla o sus
  fuentes (p. ej. «Plan no generado (LLM no accesible)»).

**Privacidad:** con un proveedor externo (Groq, Gemini…) los datos de los fallos salen a
un tercero; por eso hace falta `ALLOW_EXTERNAL_LLM=true` de forma explícita.

---

## Claves de firma de las actas (Ed25519)

Las actas firmadas (de run y de traspaso) necesitan **dos variables en el backend**. Si
faltan, `GET /v2/certificates/pubkey` devuelve `503 "clave pública de firma no
configurada"` y no se puede emitir ni verificar ningún acta.

1. Genera el par una sola vez:
   ```bash
   openssl genpkey -algorithm ed25519 -out mnemo-signing-private.pem
   openssl pkey -in mnemo-signing-private.pem -pubout -out mnemo-signing-public.pem
   ```
2. En el host del backend (Render → Environment, o la configuración del Space):
   - `MNEMO_SIGNING_PRIVATE_KEY` = contenido completo de `mnemo-signing-private.pem`
     (**como secreto**, con las líneas `-----BEGIN/END PRIVATE KEY-----`).
   - `MNEMO_SIGNING_PUBLIC_KEY` = contenido completo de `mnemo-signing-public.pem` (es
     publicable).
3. Comprueba: `GET https://<backend>/v2/certificates/pubkey` →
   `{"algorithm":"ed25519","public_key_pem":...}`.

> **Rotación:** cada acta lleva firmado el `key_id` (SHA-256 truncado de la clave pública)
> con la que se emitió. Al rotar, pon la pública anterior en
> `MNEMO_SIGNING_RETIRED_PUBLIC_KEYS` y las actas antiguas seguirán verificando. Guarda la
> privada en un gestor de secretos y no la reutilices entre entornos.

### Pie de verificación del acta en PDF (opcional)

| Variable | ¿Obligatoria? | Qué es |
|----------|----------------|--------|
| `MNEMO_PUBLIC_APP_URL` | No | URL pública del frontend (p. ej. `https://mnemo-beta-one.vercel.app`). Solo se usa para el pie «verificable en …» del acta en PDF. Sin ella, el acta no imprime host. |

---

## Webhook de CI (ingesta automática desde el CI del cliente)

Para que `POST /v2/ci/webhook` funcione (reporter de Playwright o cualquier emisor del
artefacto), el backend necesita estas variables (sin ellas responde 401/503):

| Variable | Qué es |
|----------|--------|
| `CI_WEBHOOK_SECRET` | Secreto compartido para la firma HMAC-SHA256 (`X-Hub-Signature-256`) |
| `CI_SERVICE_USER_ID` | UUID del usuario de servicio al que se atribuye la ingesta (debe ser miembro de la organización) |
| `CI_SERVICE_ORG_ID` | Opcional: si se define, el webhook rechaza (403) artefactos de cualquier otra organización |

La alternativa sin secreto compartido es `POST /v2/ci/ingest` con un token de ingesta por
organización, que se crea desde la app (Integraciones).

Relacionadas: `MNEMO_SECRET_KEY` (clave Fernet, **obligatoria si se usa la integración
Jira/Xray**: cifra las credenciales de cada organización) y las cotas `CI_MAX_BODY_BYTES` e
`INGEST_MAX_BYTES` (10 MiB por defecto; por encima → 413). Todas están en `.env.example` y
declaradas en `render.yaml`.

---

## Mantener despierto un backend gratuito

Los hosts gratuitos (HF Spaces) suspenden el backend por inactividad: la primera petición
tarda alrededor de un minuto y puede dar un 504. El workflow
**`.github/workflows/keep-warm.yml`** consulta `GET /v2/health` cada 15 minutos y falla
(con aviso por correo) si no responde 200.

Para activarlo: GitHub → Settings → Secrets and variables → Actions → **Variables** →
`BACKEND_HEALTH_URL` = `https://<backend>/v2/health`. Sin la variable, el job no hace nada.

---

## Alternativas de hosting del backend

| Host | Coste cero | RAM (torch) | Nota |
|------|----------|-------------|------|
| **Render** (esta guía) | No (plan standard) | ✅ ≥1 GB | el más directo; despliegue automático |
| **Fly.io** | casi | ✅ 1 GB configurable | `fly launch` detecta el Dockerfile; sin `$PORT` (usa 8080) |
| **Railway** | crédito inicial | ✅ flexible | sencillo; después, de pago |
| **Oracle Cloud Free** | ✅ siempre gratis | ✅ hasta 24 GB (VM ARM) | más configuración (máquina virtual sin preparar) |
| **Hugging Face Spaces** (Docker) | ✅ | ✅ 16 GB | el Space es público y se suspende; requiere `app_port: 8080` en el frontmatter del README del Space (si no, HF asume 7860) |

El `Dockerfile` escucha en `${PORT:-8080}`, así que sirve para todos (Render y Railway
inyectan `$PORT`; Fly, Oracle y HF usan 8080).

Ver también [`docs/demo/runbook.md`](../demo/runbook.md) (operativa de la demo sobre este
despliegue) y [`docs/demo/guion.md`](../demo/guion.md) (guion de la presentación).

---

## Lista de comprobación

- [ ] Todas las migraciones de `db/migrations/` aplicadas en orden (se puede comprobar que
      RLS está activo con `relrowsecurity` en `pg_class`).
- [ ] `GET https://<backend>/v2/health` responde 200.
- [ ] `GET https://<backend>/v2/certificates/pubkey` responde 200 con la clave pública (las
      actas firmadas están operativas).
- [ ] `NEXT_PUBLIC_API_BASE_URL` en Vercel apunta al backend (sin barra final) y el
      frontend se ha vuelto a desplegar.
- [ ] En la app, la pestaña Network del navegador muestra `/api/v2/orgs` con **200** (no
      500/502), y crear una organización funciona.
- [ ] (Si el host se suspende) variable `BACKEND_HEALTH_URL` creada en GitHub y el
      workflow keep-warm en verde.
