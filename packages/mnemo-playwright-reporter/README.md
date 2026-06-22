# mnemo-playwright-reporter

Reporter + auto-fixture de Playwright que envía los resultados de cada run (estado,
reintentos, error y **DOM** por test) a Mnemo Autopilot (`POST /v2/ci/webhook`),
firmados con HMAC. Convierte la ingesta de QA en "viva desde el CI".

## Instalación

```bash
# El paquete se consume compilado desde el monorepo; ejecuta npm run build
# una vez para generar dist/ (no se publica en un registro público).
npm run build
```

## Uso

1. Importa `test` desde el paquete en tus specs (en vez de `@playwright/test`):

```ts
import { test, expect } from "mnemo-playwright-reporter";
```

2. Añade el reporter en `playwright.config.ts`:

```ts
export default defineConfig({
  reporter: [["list"], ["mnemo-playwright-reporter"]],
});
```

3. Configura por variables de entorno (en el CI):

| Variable | Descripción |
|---|---|
| `MNEMO_WEBHOOK_URL` | URL de `/v2/ci/webhook` del backend Mnemo |
| `MNEMO_WEBHOOK_SECRET` | Secreto HMAC compartido (= `CI_WEBHOOK_SECRET` del backend) |
| `MNEMO_ORG_ID` | UUID de la organización |
| `MNEMO_PROJECT` | Nombre del proyecto |
| `MNEMO_COMMIT_SHA` o `GITHUB_SHA` | Commit del run |

Si falta cualquier variable, el reporter **no envía nada** y no rompe el run.
