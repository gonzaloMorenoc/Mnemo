# mnemo-playwright-reporter

Reporter + auto-fixture de Playwright que envía los resultados de cada run (estado,
reintentos, error y **DOM** por test) a Mnemo Autopilot (`POST /v2/ci/webhook`),
firmados con HMAC. Convierte la ingesta de QA en "viva desde el CI".

## Instalación (no publicado en npm)

El paquete se consume compilado desde este monorepo:

```bash
cd packages/mnemo-playwright-reporter
npm install && npm run build   # genera dist/
```

y en el proyecto de tests, referencia local en su `package.json`:

```json
{ "devDependencies": { "mnemo-playwright-reporter": "file:../packages/mnemo-playwright-reporter" } }
```

(alternativa: `npm pack` aquí y `npm install ../mnemo-playwright-reporter-0.1.0.tgz` allí).

## Uso

1. Importa `test` desde el paquete en tus specs (en vez de `@playwright/test`):

```ts
import { test, expect } from "mnemo-playwright-reporter";
```

2. Añade el reporter en `playwright.config.ts` (por env vars, o con opciones inline):

```ts
export default defineConfig({
  reporter: [["list"], ["mnemo-playwright-reporter"]],
  // — o con opciones programáticas (tienen prioridad sobre las env vars):
  // reporter: [["mnemo-playwright-reporter", { url, secret, orgId, project, commitSha, runUid }]],
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
| `MNEMO_RUN_UID` *(opcional)* | Identificador único del run para la **deduplicación** |

Si falta cualquier variable requerida, el reporter **no envía nada** y no rompe el run.

## Deduplicación (`run_uid`)

El backend deduplica por `(org_id, run_uid)`: re-entregar el mismo run (retry del
webhook, re-run del job) devuelve el run original en vez de ingerirlo dos veces.
El reporter resuelve el `run_uid` así:

1. Opción programática `runUid`.
2. `MNEMO_RUN_UID`.
3. En GitHub Actions, automático: `gh-<GITHUB_RUN_ID>-<GITHUB_RUN_ATTEMPT>`.
4. Sin ninguna fuente → `null` (el backend NO deduplica: cada envío crea un run).

## Semántica de estados

- `pass` con `retry > 0` → se reporta como **`flaky`** (pasó al reintentar).
- `timedOut` / `interrupted` → **`fail`**.
- Se conserva el **intento final** de cada test (no los intermedios).

## Límites del backend

El webhook impone cotas por campo (`message` 100 k, `trace` 200 k, `dom` 5 MB) y una
cota total de cuerpo (`CI_MAX_BODY_BYTES`, 10 MiB por defecto): un DOM enorme puede
hacer que el artefacto entero sea rechazado (413/422). Si tus páginas son muy grandes,
considera recortar el DOM capturado en la fixture.
