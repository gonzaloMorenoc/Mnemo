# Spec — Mnemo Autopilot F1b: `mnemo-playwright-reporter`

**Fecha:** 2026-06-22
**Rama:** `feat/mnemo-playwright-reporter` (desde `main`)
**Contexto:** F1b del plan de Mnemo Autopilot (`docs/superpowers/specs/2026-06-22-mnemo-autopilot-design.md`, §6.4 y §19). El backend de ingesta viva (F1) está en PR #11: `POST /v2/ci/webhook` que verifica HMAC y consume el `CiRunArtifact`. F1b es el productor de ese artefacto desde el CI.

---

## 1. Objetivo y no-objetivos

**Objetivo:** un paquete npm (TypeScript) — un **reporter de Playwright** + un **auto-fixture** — que el repo de tests del cliente instala. Captura el resultado y el DOM de cada test, ensambla el `CiRunArtifact`, lo **firma con HMAC-SHA256** y lo **POSTea** a `/v2/ci/webhook`. Es el punto de integración que convierte la ingesta de "subida manual" en "viva desde el CI".

**No-objetivos (YAGNI):**
- Repo de demo de Playwright (es F6).
- Publicación al registry npm público.
- Multi-página / multi-context (captura la página principal del test).
- Reintentos/cola de POST (failure-safe basta para F1b).
- Conectores no-Playwright (Cypress/Selenium son roadmap).

## 2. Contrato (debe casar con el backend F1)

El artefacto y la firma deben ser **byte-compatibles** con lo implementado en F1:

```ts
type CiTestResult = {
  test_name: string;
  status: "pass" | "fail" | "flaky" | "skipped";
  retried: boolean;            // default false
  error_type?: string | null;
  message?: string | null;
  trace?: string | null;
  file?: string | null;
  line?: number | null;
  dom?: string | null;
};
type CiRunArtifact = {
  project: string;
  org_id: string;
  commit_sha: string;
  source: string;              // "playwright"
  tests: CiTestResult[];
};
```

- **Firma:** `body = JSON.stringify(artifact)`; cabecera `X-Hub-Signature-256: sha256=<hmac_sha256_hex(secret, body)>`. Se firma y se envía **exactamente el mismo string** (el backend verifica sobre el cuerpo crudo y luego `model_validate_json`). Algoritmo idéntico a `src/ci/webhook_auth.py` (HMAC-SHA256, prefijo `sha256=`, hex).
- El backend ignora claves extra (Pydantic), pero el artefacto debe incluir los campos requeridos (`project`, `org_id`, `commit_sha`, `tests`).
- `kind` del DOM lo decide el backend por `status` (pass→`last_green`, resto→`failure`); el reporter solo manda `dom` cuando lo capturó.

## 3. Arquitectura — lógica pura separada de I/O

```
packages/mnemo-playwright-reporter/
├── src/
│  ├── types.ts      # CiTestResult, CiRunArtifact, MnemoConfig
│  ├── artifact.ts   # PURO: buildTestResult(input)→CiTestResult; buildArtifact(results,meta)→CiRunArtifact
│  ├── sign.ts       # PURO: sign(body,secret)→"sha256=<hex>"  (crypto.createHmac)
│  ├── config.ts     # resolveConfig(env,options)→MnemoConfig|null  (incompleto→null)
│  ├── post.ts       # I/O: postArtifact(config,artifact)→Promise<void>  (firma+fetch, failure-safe)
│  ├── reporter.ts   # MnemoReporter implements Reporter: onTestEnd acumula; onEnd→build+post
│  ├── fixture.ts    # test.extend: auto-fixture captura page.content()→testInfo.attach('mnemo-dom')
│  └── index.ts      # export { test } (fixture) y export default MnemoReporter
├── tests/           # vitest
├── package.json · tsconfig.json · vitest.config.ts · README.md
```

**Principio:** todo lo testeable sin runtime de Playwright vive en funciones puras (`artifact`, `sign`, `config`) o con I/O mockeable (`post`). `reporter` y `fixture` son orquestación fina.

## 4. Componentes (interfaces claras)

| Módulo | Responsabilidad | Interfaz |
|---|---|---|
| `types.ts` | tipos del contrato + `MnemoConfig` | `MnemoConfig = {url, secret, orgId, project, commitSha}` |
| `artifact.ts` | mapear resultado Playwright → contrato | `buildTestResult(in: TestResultInput) → CiTestResult`; `buildArtifact(results, meta) → CiRunArtifact` |
| `sign.ts` | firma HMAC | `sign(body: string, secret: string) → string` (`"sha256="+hex`) |
| `config.ts` | resolver config de env+opciones | `resolveConfig(env, options?) → MnemoConfig \| null` |
| `post.ts` | enviar (failure-safe) | `postArtifact(config: MnemoConfig, artifact: CiRunArtifact, fetchImpl?) → Promise<void>` |
| `reporter.ts` | reporter Playwright | `class MnemoReporter implements Reporter` (`onTestEnd`, `onEnd`) |
| `fixture.ts` | captura DOM | `export const test = base.extend({ _mnemoDom: [auto, {auto:true}] })` |

`TestResultInput` es la forma mínima que `artifact.ts` necesita (test_name, status, retried, error fields, dom) — NO el objeto `TestCase`/`TestResult` completo de Playwright. El `reporter` extrae esa forma de los objetos de Playwright y llama a la función pura → así `artifact.ts` se testea con objetos plain.

## 5. Mapeo Playwright → `CiTestResult` (en `reporter.onTestEnd`)

**Dedup por reintentos:** Playwright llama `onTestEnd` **una vez por intento** (cada retry es un `TestResult`). El reporter acumula **un solo `CiTestResult` por test** (clave: `test.id`), quedándose con el intento **final** (mayor `result.retry`). De ahí derivan: `retried = result.retry > 0`; `flaky = hubo un intento previo fallido pero el final pasó` (equivalente a `test.outcome() === 'flaky'`). El DOM tomado es el del intento final.

- `test_name`: `test.titlePath().join(' > ')` (o `test.title`).
- `status`: de `result.status` (`passed`→`pass`, `failed`/`timedOut`→`fail`, `skipped`→`skipped`) + **`flaky`** si `result.retry > 0 && result.status === 'passed'` (pasó tras reintento) o status flaky de Playwright.
- `retried`: `result.retry > 0`.
- `error_type`/`message`/`trace`: de `result.error` (`error.message`, `error.stack`). `error_type` best-effort del primer token tipo `XxxError` del mensaje (espejo de `parse_error_type`).
- `file`/`line`: de `test.location`.
- `dom`: del attachment `mnemo-dom` en `result.attachments` (si el fixture lo adjuntó).

## 6. Captura de DOM (fixture)

Auto-fixture (`test.extend`) que tras el cuerpo del test hace `const html = await page.content(); await testInfo.attach('mnemo-dom', { body: html, contentType: 'text/html' })`. El demo/cliente importa `test` desde el paquete en vez de `@playwright/test`. Captura la página principal; envuelto en try/catch para no afectar el resultado del test.

## 7. Config y failure-safe (crítico)

- **Env (CI-friendly):** `MNEMO_WEBHOOK_URL`, `MNEMO_WEBHOOK_SECRET`, `MNEMO_ORG_ID`, `MNEMO_PROJECT`, commit de `MNEMO_COMMIT_SHA || GITHUB_SHA`. Las opciones del reporter en `playwright.config.ts` tienen prioridad sobre env.
- `resolveConfig` devuelve `null` si falta cualquier requerido → el reporter **no-opera** (warn) sin romper el run.
- **Un reporter NUNCA tumba el CI:** config incompleta o POST fallido → `console.warn('[mnemo] ...')` y continúa. Cero excepciones propagadas desde `onEnd`/`post`.

## 8. Testing (vitest, sin runtime de Playwright)

- `artifact`: `buildTestResult` mapea cada status/retry/error correctamente (incl. flaky por retry+passed); `buildArtifact` ensambla con meta. Objetos plain.
- `sign`: HMAC de un `(body, secret)` conocido produce el `sha256=<hex>` esperado. **Cross-check de interoperabilidad:** el mismo `(body, secret)` debe dar el MISMO hex que `hmac.new(secret, body, sha256).hexdigest()` de Python (valor fijado en el test).
- `config`: env completo → config; falta uno → `null`; opciones sobreescriben env.
- `post`: con `fetch` mockeado — cabecera `X-Hub-Signature-256` correcta, `body` === lo firmado, `Content-Type: application/json`; ante `fetch` que rechaza o status !=2xx → no lanza (failure-safe), warn emitido.
- Cobertura de las ramas failure-safe (config null → no fetch; fetch error → swallow).

## 9. Packaging

- TypeScript 5, target Node 18+ (CI). Build con `tsc` a `dist/` (ESM + types). `package.json` con `exports` para el default (reporter) y `./fixture` (o ambos desde `index`).
- vitest 4 (consistente con el frontend del repo). `peerDependencies`: `@playwright/test`.
- README: cómo instalar, el cambio de import (`test`), añadir `MnemoReporter` a `playwright.config.ts`, y las variables de entorno.

## 10. Criterios de aceptación

- [ ] `npm run test` (vitest) verde: artifact/sign/config/post cubiertos.
- [ ] `sign` produce el mismo HMAC que el backend Python para un vector fijo (interoperabilidad demostrada en test).
- [ ] `buildTestResult` mapea pass/fail/skipped/flaky(retry+passed)/retried y extrae error_type/message/file/line/dom.
- [ ] `resolveConfig` devuelve `null` ante config incompleta; el reporter no-opera sin romper.
- [ ] `postArtifact` firma correctamente y es failure-safe (no lanza ante error de red/status).
- [ ] `tsc --noEmit` y lint limpios; `tsc` build genera `dist/` con tipos.
- [ ] README con instalación, import del `test`, config del reporter y env vars.

## 11. Cómo encaja con F2+

El reporter alimenta `test_results` (status/retry/SHA), `dom_snapshots` (DOM) y el Defect DNA (fallos) — exactamente las señales que F2 (triaje determinista: intermitencia mismo-SHA, "DOM cambió") y F3 (self-heal) consumen. Sin reporter no hay ingesta viva real; con él, el ciclo CI→Mnemo es automático.
