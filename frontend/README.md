# Mnemo — Frontend (Next.js)

Frontend web de **Mnemo** con Next.js (App Router), Tailwind + shadcn/ui, autenticación Supabase y TanStack Query. Es **solo cliente**: el dato, el LLM, los embeddings y la firma viven en el backend; el frontend habla con él a través de un **proxy server-side**.

## Stack

- Next.js 16 (App Router) + React 19 + TypeScript
- TailwindCSS 4 + componentes estilo shadcn/ui
- Supabase JS (auth de cliente)
- TanStack Query
- react-hook-form + zod
- lucide-react · framer-motion · sonner
- Vitest + Testing Library

## Rutas

`/` · `/login` · `/signup` · **`/verify`** (verificación pública de actas, sin login) ·
`/app` · `/app/assurance` · `/app/autopilot` · `/app/calibration` · `/app/defects` ·
`/app/graph` · `/app/integrations` · `/app/knowledge` · `/app/onboarding` · `/app/org` ·
`/app/settings` · `/app/test-plan`

## Cómo habla con el backend (proxy server-side)

El frontend **no** llama al backend directamente desde el navegador. Llama a sus propias rutas `/api/v2/*` (route handlers en `src/app/api/`), que reenvían (`src/lib/server/proxy.ts`) al backend en `NEXT_PUBLIC_API_BASE_URL`. Ventaja: sin CORS y la URL del backend se resuelve en el servidor. Por eso `next.config.ts` no necesita `rewrites`.

## Variables de entorno

Copia `.env.example` en `.env.local` y rellena:

- `NEXT_PUBLIC_API_BASE_URL` — URL del backend (p. ej. `http://localhost:8000` en local).
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

## Scripts

- `npm run dev` — servidor de desarrollo
- `npm run build` — build de producción
- `npm run start` — servidor de producción
- `npm run lint` / `lint:ci` — ESLint
- `npm run typecheck` / `typecheck:ci` — chequeo de tipos
- `npm run test` / `test:ci` — Vitest
- `npm run check:ci` — lint + test + build (lo que corre CI)

## CI

- Versión de Node fijada en `.nvmrc` (`22.14.0`) y comportamiento de npm en `.npmrc`.
- Workflow en `.github/workflows/` (se dispara solo cuando cambian archivos del frontend).

## Despliegue (Vercel)

El proyecto vive en este subdirectorio, así que en Vercel hay que fijar **Root Directory = `frontend`** (si no, Vercel detecta el backend FastAPI de la raíz y el build falla). Framework **Next.js** (autodetectado), **Node 22.x**. Configura las 3 variables `NEXT_PUBLIC_*` en el proyecto de Vercel. Ver la sección *Despliegue* del [README raíz](../README.md).
