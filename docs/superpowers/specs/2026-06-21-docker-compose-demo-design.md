# docker-compose on-prem + demo sembrada

**Fecha:** 2026-06-21
**Estado:** Diseño aprobado (pendiente de plan de implementación)

## Contexto

Mnemo tiene un MVP completo (ingesta de 7 formatos + Jira, Defect DNA, veredicto, causa
raíz con LLM intercambiable) pero **no se puede enseñar de un comando**: el backend usa
Supabase (Postgres+pgvector + auth GoTrue/JWKS) en la nube, y arrancar todo a mano (BD,
Ollama, backend, frontend, seed) es frágil. Para el concurso MTP AI Innovation Award, un
jurado debe **ver** Mnemo funcionando y, sobre todo, ver que es **on-prem/privado** (el
pitch). Hoy nada de eso es reproducible.

La auth está acoplada a Supabase: `src/security.py::SupabaseJWTVerifier` valida JWT
**RS256** contra el JWKS de `SUPABASE_URL/auth/v1/.well-known/jwks.json`, y el frontend usa
Supabase Auth para el login.

## Objetivo

Un `docker-compose.yml` que levante **todo el stack en local** (Supabase self-hosted +
Ollama + backend + frontend), aplique migraciones y siembre una demo, de modo que
`docker compose up` → abrir el navegador → subir un reporte → ver el Defect DNA → "Analizar
causa raíz" funcione sin tocar nada externo. On-prem real: ningún dato sale a la nube.

## Alcance

**Incluido:**
- `docker-compose.yml` con: Supabase self-hosted (subconjunto: Postgres+pgvector, GoTrue,
  Kong), Ollama, backend, frontend, y un servicio de init (migraciones + seed + usuario demo).
- `Dockerfile` (backend) y `frontend/Dockerfile`, con `.dockerignore`.
- `.env.docker` con valores **solo de demo** (sin secretos reales).
- Configuración de GoTrue para firmar **RS256 + JWKS** (compatibilidad con el verifier sin
  cambiar código), o el fallback HS256 documentado.
- `docs/DEMO.md` con el paso a paso.
- Una verificación de arranque (script o checklist) de que el flujo e2e funciona.

**Fuera de alcance:**
- Orquestación de producción (Kubernetes, Helm), TLS/HTTPS, backups, alta disponibilidad,
  escalado horizontal.
- El resto del stack de Supabase (Storage, Realtime, Studio, Edge Functions) — Mnemo no los usa.
- Cambiar el camino de auth de la app (se mantiene Supabase/GoTrue, no se introduce un modo demo).
- Probar el compose en el CI (es demasiado pesado: ~5 GB de modelo + imágenes).

## Arquitectura

```
                         docker compose up
  ┌──────────────────────────────────────────────────────────────────┐
  │  kong (gateway :8000)  ── /auth/v1/* ──►  auth (GoTrue)            │
  │        ▲                                      │ firma JWT RS256    │
  │        │ JWKS                                 ▼                    │
  │  frontend (Next.js :3000) ── /api/v2/* ─► backend (FastAPI :8080) │
  │                                               │                    │
  │                              ┌────────────────┼─────────┐         │
  │                              ▼                ▼         ▼         │
  │                          db (Postgres        ollama   (init:      │
  │                          + pgvector)         :11434   migraciones │
  │                                                        + seed)    │
  └──────────────────────────────────────────────────────────────────┘
   Todo en la red de Docker; nada sale a Internet salvo (opcional) el pull del modelo.
```

## Componentes (servicios del compose)

### `db` — Postgres + pgvector
Imagen `supabase/postgres:<pin>` (incluye pgvector y las extensiones que usan las
migraciones). Volumen `db-data` para persistencia. Healthcheck `pg_isready`. Inicializa los
roles que GoTrue y la app esperan (el rol `postgres` del pooler; la app conecta con
`DATABASE_URL` local).

### `auth` (GoTrue) + `kong`
- `auth`: `supabase/gotrue:<pin>`. Configurado para emitir JWT **RS256** con un par de claves
  generado para la demo, y exponer el JWKS. `GOTRUE_SITE_URL`, `GOTRUE_DISABLE_SIGNUP=false`.
- `kong`: `supabase/kong:<pin>` enruta `/auth/v1/*` (incl. `.well-known/jwks.json`) a GoTrue.
  Es el host que `SUPABASE_URL`/`SUPABASE_JWKS_URL` del backend apuntan (`http://kong:8000`).

### `ollama`
`ollama/ollama:<pin>`, volumen `ollama-models`. El init hace `ollama pull deepseek-r1:8b`
(o se documenta para que el usuario lo lance). El backend usa `OLLAMA_BASE_URL=http://ollama:11434`
y `LLM_PROVIDER=ollama` (0 €/privado por defecto).

### `backend` — `Dockerfile` nuevo
Python 3.13 slim · `pip install -r requirements.txt` · copia `src/`, `api.py`, `db/`,
`scripts/` · `CMD uvicorn api:app --host 0.0.0.0 --port 8080`. Variables: `DATABASE_URL`
(→ `db`), `SUPABASE_URL`/`SUPABASE_JWKS_URL` (→ `kong`), `OLLAMA_BASE_URL`, `MNEMO_SECRET_KEY`.
Healthcheck `GET /v2/health`. `depends_on` db/kong/ollama sanos.

### `frontend` — `frontend/Dockerfile` nuevo
Multi-stage: `npm ci` + `npm run build`, luego `npm run start`. Variables de build/runtime:
`NEXT_PUBLIC_API_BASE_URL` (→ backend), `NEXT_PUBLIC_SUPABASE_URL` (→ kong),
`NEXT_PUBLIC_SUPABASE_ANON_KEY` (la anon key de la demo). Expone `:3000`.

### `init` — migraciones + seed + usuario demo
Servicio efímero que: (1) espera a `db` sano; (2) aplica las migraciones `db/migrations/001..006`
en orden (reutiliza un pequeño runner Python con psycopg, idempotente — las migraciones ya
usan `if exists`/`if not exists` donde aplica); (3) crea el usuario demo vía la **API de
GoTrue** (`POST /auth/v1/signup` con `demo@mnemo.local` + contraseña conocida) para que tenga
credenciales reales de login; (4) corre una variante de `scripts/seed_demo.py` que usa ese
`user_id` para crear la org y sembrar reportes (la familia compartida cross-proyecto). Es
idempotente: re-`up` no duplica (signup existente → ok; seed comprueba antes de insertar).

## Compatibilidad de JWT (decisión técnica)

El verifier exige **RS256 + JWKS**. **Enfoque elegido:** configurar GoTrue self-hosted para
firmar con RS256 y publicar el JWKS (las "JWT signing keys" asimétricas de Supabase). Así el
backend valida los tokens locales sin cambiar una línea. Si en implementación esa
configuración resulta inviable con las imágenes disponibles, el **fallback** es un añadido
mínimo y aislado al verifier: aceptar HS256 con `SUPABASE_JWT_SECRET` cuando esté definido
(un `if` extra en `SupabaseJWTVerifier.verify`, sin tocar el resto). El plan validará el
enfoque RS256 primero y solo caerá al fallback si falla.

## Datos / secretos

`.env.docker` (commiteable, **solo demo**): contraseña de `db`, `JWT` keys (par RSA generado
para la demo), `ANON_KEY`/`SERVICE_ROLE_KEY` de Supabase, `MNEMO_SECRET_KEY` (Fernet),
credenciales del usuario demo. Un comentario deja claro que NO son secretos de producción.
El `.env` real (gitignored) no se toca.

## Flujo de la demo (docs/DEMO.md)

1. `docker compose up -d` (la primera vez baja imágenes + el modelo ~5 GB; tarda).
2. Esperar a que `backend` esté sano (`/v2/health`).
3. Abrir `http://localhost:3000`, login `demo@mnemo.local` / contraseña demo.
4. Ver el **Defect DNA** ya sembrado (familias cross-proyecto); abrir una familia y pulsar
   **"Analizar causa raíz"** (Ollama local).
5. Subir un reporte Allure/JUnit de `examples/` en **Assurance** y ver el veredicto.

## Manejo de errores / robustez

- `healthcheck` + `depends_on: condition: service_healthy` para orden de arranque.
- El init es idempotente y falla ruidosamente si una migración no aplica.
- Volúmenes persistentes (`db-data`, `ollama-models`) para no re-descargar/re-sembrar.
- Si Ollama aún no tiene el modelo, "Analizar causa raíz" degrada con un mensaje claro (ya
  implementado: 503).

## Testing / verificación

- No hay tests unitarios nuevos de la app (es infraestructura). La verificación es:
  - `docker compose config` valida la sintaxis del compose.
  - Los `Dockerfile` construyen (build).
  - Un **smoke e2e manual** (o un script `scripts/smoke_demo.sh`): tras `up`, comprobar
    `GET /v2/health` 200, que el login demo devuelve un JWT que el backend acepta (un
    `GET /v2/defects` autenticado responde 200), y que `list_defects` trae la familia sembrada.
- El CI **no** ejecuta el compose (demasiado pesado); el spec lo deja explícito.

## Riesgo operativo

El disco de la máquina de desarrollo está al límite (~96 %). Construir las imágenes + el
modelo de Ollama (~5 GB) + el volumen de Postgres requiere **liberar espacio antes** de
probar el compose. El diseño/plan no dependen del disco; la **prueba local sí**. Se documenta
el requisito de espacio en `docs/DEMO.md`.

## Decisiones de diseño

- **Supabase self-hosted (subconjunto db+auth+kong)** en vez de Postgres + auth mock: cero
  cambios en el camino de auth de la app y fidelidad con producción; se omite el resto del
  stack Supabase por peso (YAGNI).
- **RS256+JWKS en GoTrue** para no tocar el verifier; fallback HS256 acotado si fuese necesario.
- **Init idempotente** que crea el usuario demo vía GoTrue (no por inserción directa) para que
  el login real funcione en la demo.
- **`.env.docker` commiteable** con secretos de demo: arranque sin configuración manual.
- **CI no prueba el compose**: el coste (modelo 5 GB) no compensa; smoke manual documentado.
