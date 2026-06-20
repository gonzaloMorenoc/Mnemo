# TraceFix Frontend (Next.js)

Modern web frontend for TraceFix using Next.js App Router, Tailwind, shadcn/ui patterns, Supabase auth, and TanStack Query.

## Tech Stack

- Next.js (App Router) + TypeScript
- TailwindCSS + shadcn/ui-style components
- Supabase JS (client auth)
- TanStack Query
- react-hook-form + zod
- lucide-react
- framer-motion
- Vitest + Testing Library

## Routes

- `/`
- `/login`
- `/signup`
- `/app/analyze`
- `/app/knowledge`
- `/app/org`
- `/app/settings`

## Environment Variables

Copy `.env.example` into `.env.local` and set:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

## Scripts

- `npm run dev` - start dev server
- `npm run build` - production build
- `npm run start` - run production server
- `npm run lint` - run ESLint
- `npm run lint:ci` - run ESLint with GitHub annotations format
- `npm run typecheck` - run TypeScript type checks
- `npm run typecheck:ci` - deterministic TypeScript check for CI
- `npm run test` - run UI tests (Vitest)
- `npm run test:ci` - Vitest single-fork mode for CI stability
- `npm run check:ci` - lint + test + build (build includes Next.js type validation)

## CI Hardening

- Node version pinned in `/Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend/.nvmrc` (`22.14.0`).
- npm behavior pinned via `/Users/gonzalo/Documents/GitHub/SmartErrorDebugger/frontend/.npmrc`.
- GitHub Actions workflow at `/Users/gonzalo/Documents/GitHub/SmartErrorDebugger/.github/workflows/frontend-ci.yml`.
- Workflow triggers only when frontend files (or workflow file) change.

## API Notes

Implemented against existing backend endpoints:

- `GET /health`
- `GET /v2/orgs`
- `POST /v2/orgs`
- `POST /v2/orgs/join`
- `POST /v2/upload`
- `POST /v2/analyze`

Missing APIs are surfaced in UI as clear placeholders:

- `GET /v2/knowledge/documents?scope=&org_id=`
- `DELETE /v2/knowledge/documents/:id`
- `GET /v2/orgs/:org_id/members`
- `PATCH /v2/orgs/:org_id/members/:user_id`
- `POST /v2/analyses/:id/feedback`
