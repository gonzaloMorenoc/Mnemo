---
title: Mnemo Backend
emoji: 🧠
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8080
pinned: false
---

# Mnemo — backend (FastAPI)

Backend de **Mnemo** desplegado como Docker Space. El frontend (en Vercel) lo consume vía
`NEXT_PUBLIC_API_BASE_URL`. El código se clona del repo público en build (ver `Dockerfile`).

## Configuración (Settings → Variables and secrets)

**Secrets** (sensibles):
- `DATABASE_URL` — cadena de conexión de Supabase (modo pooler/transaction).
- `SUPABASE_URL` — `https://<proyecto>.supabase.co`
- `SUPABASE_JWKS_URL` — `https://<proyecto>.supabase.co/auth/v1/.well-known/jwks.json`
- `OPENAI_API_KEY` — tu API key de Groq (console.groq.com/keys)

**Variables** (no sensibles):
- `SUPABASE_JWT_AUDIENCE=authenticated`
- `LLM_PROVIDER=openai`
- `ALLOW_EXTERNAL_LLM=true`
- `OPENAI_BASE_URL=https://api.groq.com/openai/v1`
- `LLM_MODEL=llama-3.3-70b-versatile`

Comprueba el arranque en `https://<usuario>-<space>.hf.space/v2/health`.
Guía completa: `docs/deploy/produccion.md` en el repo.
