# Mnemo Autopilot — F1b: `mnemo-playwright-reporter` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un paquete npm (reporter de Playwright + auto-fixture) que captura el resultado y el DOM de cada test, ensambla el `CiRunArtifact`, lo firma con HMAC y lo POSTea a `/v2/ci/webhook` — convirtiendo la ingesta en "viva desde el CI".

**Architecture:** Lógica pura (`artifact`, `sign`, `config`) separada de I/O (`post`), testeable con vitest sin runtime de Playwright. El `reporter` (clase `Reporter`) y el `fixture` (`test.extend` que adjunta el DOM) son orquestación fina. Failure-safe por diseño: nunca lanza ni tumba el CI.

**Tech Stack:** TypeScript 5, CommonJS, Node 18+ (CI: Node 22), vitest 4, `@playwright/test` (peer dependency).

## Global Constraints

- Paquete en `packages/mnemo-playwright-reporter/`. Primer paquete TS independiente del repo (el frontend usa TS 5 + vitest 4 — mismas versiones).
- **Byte-compatibilidad con el backend F1** (`src/ci/models.py`, `src/ci/webhook_auth.py`): firma `X-Hub-Signature-256: sha256=<hmac_sha256_hex(secret, body)>`, firmando **el MISMO string** que se envía como `body`. Campos del contrato en **snake_case** (`test_name`, `org_id`, `commit_sha`, `error_type`, ...). `source` siempre `"playwright"`.
- **Failure-safe (crítico):** el reporter NUNCA lanza ni hace fallar el run. Config incompleta o POST fallido → `console.warn('[mnemo] ...')` y continuar.
- TDD: test primero. Inmutabilidad: no mutar las entradas.
- Lógica pura separada de I/O; archivos pequeños y enfocados.
- Vector de interop verificado (Python == Node): para `secret="mnemo-test-secret"` y `body='{"project":"demo","org_id":"org-1","commit_sha":"abc123","source":"playwright","tests":[]}'`, la firma es `sha256=5eff407fdd992b247c9e7107e4ee38873454f47717311dab75f7e2f748377a88`.

---

### Task 1: Scaffold del paquete + tipos + firma HMAC

**Files:**
- Create: `packages/mnemo-playwright-reporter/package.json`
- Create: `packages/mnemo-playwright-reporter/tsconfig.json`
- Create: `packages/mnemo-playwright-reporter/vitest.config.ts`
- Create: `packages/mnemo-playwright-reporter/.gitignore`
- Create: `packages/mnemo-playwright-reporter/src/types.ts`
- Create: `packages/mnemo-playwright-reporter/src/sign.ts`
- Test: `packages/mnemo-playwright-reporter/tests/sign.test.ts`

**Interfaces:**
- Produces: tipos `CiTestResult`, `CiRunArtifact`, `MnemoConfig`, `TestResultInput`, `ArtifactMeta`, `CiStatus` (`src/types.ts`); `sign(body: string, secret: string) -> string` que devuelve `"sha256="+hex` (`src/sign.ts`).

> Trabaja desde `packages/mnemo-playwright-reporter/` para los comandos npm.

- [ ] **Step 1: Crear el scaffold** (package.json, tsconfig, vitest.config, .gitignore)

`package.json`:
```json
{
  "name": "mnemo-playwright-reporter",
  "version": "0.1.0",
  "description": "Playwright reporter + fixture que envía resultados y DOM a Mnemo (/v2/ci/webhook).",
  "license": "MIT",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "files": ["dist"],
  "scripts": {
    "build": "tsc",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "peerDependencies": {
    "@playwright/test": ">=1.40.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0",
    "typescript": "^5",
    "vitest": "^4.0.18"
  }
}
```

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "CommonJS",
    "moduleResolution": "Node",
    "declaration": true,
    "outDir": "dist",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}
```

`vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "node", include: ["tests/**/*.test.ts"] },
});
```

`.gitignore`:
```
node_modules
dist
```

- [ ] **Step 2: Escribir el test de firma (interop con backend Python)**

`tests/sign.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { sign } from "../src/sign";

describe("sign", () => {
  it("produce el mismo HMAC que el backend Python (interop)", () => {
    const body =
      '{"project":"demo","org_id":"org-1","commit_sha":"abc123","source":"playwright","tests":[]}';
    // Valor fijado con hmac.new(secret, body, sha256).hexdigest() en Python.
    expect(sign(body, "mnemo-test-secret")).toBe(
      "sha256=5eff407fdd992b247c9e7107e4ee38873454f47717311dab75f7e2f748377a88",
    );
  });

  it("cambia si cambia el cuerpo", () => {
    expect(sign("a", "k")).not.toBe(sign("b", "k"));
  });
});
```

- [ ] **Step 3: Instalar deps y verificar que el test falla**

Run: `cd packages/mnemo-playwright-reporter && npm install && npx vitest run tests/sign.test.ts`
Expected: FAIL — `Failed to resolve import "../src/sign"` (aún no existe).

- [ ] **Step 4: Escribir los tipos y la firma**

`src/types.ts`:
```ts
export type CiStatus = "pass" | "fail" | "flaky" | "skipped";

export interface CiTestResult {
  test_name: string;
  status: CiStatus;
  retried: boolean;
  error_type?: string | null;
  message?: string | null;
  trace?: string | null;
  file?: string | null;
  line?: number | null;
  dom?: string | null;
}

export interface CiRunArtifact {
  project: string;
  org_id: string;
  commit_sha: string;
  source: string;
  tests: CiTestResult[];
}

export interface MnemoConfig {
  url: string;
  secret: string;
  orgId: string;
  project: string;
  commitSha: string;
}

/** Forma mínima que el builder necesita (independiente de Playwright). */
export interface TestResultInput {
  testName: string;
  status: CiStatus;
  retried: boolean;
  errorType?: string | null;
  message?: string | null;
  trace?: string | null;
  file?: string | null;
  line?: number | null;
  dom?: string | null;
}

export interface ArtifactMeta {
  project: string;
  orgId: string;
  commitSha: string;
}
```

`src/sign.ts`:
```ts
import { createHmac } from "crypto";

/** Firma HMAC-SHA256 del cuerpo (mismo algoritmo que verify_signature del backend). */
export function sign(body: string, secret: string): string {
  return "sha256=" + createHmac("sha256", secret).update(body, "utf8").digest("hex");
}
```

- [ ] **Step 5: Verificar que el test pasa + typecheck**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/sign.test.ts && npx tsc --noEmit`
Expected: 2 tests PASS; tsc sin errores.

- [ ] **Step 6: Commit**

```bash
git add packages/mnemo-playwright-reporter/package.json packages/mnemo-playwright-reporter/package-lock.json packages/mnemo-playwright-reporter/tsconfig.json packages/mnemo-playwright-reporter/vitest.config.ts packages/mnemo-playwright-reporter/.gitignore packages/mnemo-playwright-reporter/src/types.ts packages/mnemo-playwright-reporter/src/sign.ts packages/mnemo-playwright-reporter/tests/sign.test.ts
git commit -m "feat(reporter): scaffold del paquete + tipos + firma HMAC"
```

---

### Task 2: Builder del artefacto (puro)

**Files:**
- Create: `packages/mnemo-playwright-reporter/src/artifact.ts`
- Test: `packages/mnemo-playwright-reporter/tests/artifact.test.ts`

**Interfaces:**
- Consumes: `CiTestResult`, `CiRunArtifact`, `TestResultInput`, `ArtifactMeta` (`src/types.ts`, Task 1).
- Produces: `buildTestResult(input: TestResultInput) -> CiTestResult`; `buildArtifact(results: TestResultInput[], meta: ArtifactMeta) -> CiRunArtifact` (`source` siempre `"playwright"`).

- [ ] **Step 1: Escribir los tests**

`tests/artifact.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { buildArtifact, buildTestResult } from "../src/artifact";

describe("buildTestResult", () => {
  it("mapea camelCase de entrada a snake_case del contrato y rellena nulls", () => {
    const r = buildTestResult({ testName: "login", status: "fail", retried: false, message: "boom" });
    expect(r).toEqual({
      test_name: "login",
      status: "fail",
      retried: false,
      error_type: null,
      message: "boom",
      trace: null,
      file: null,
      line: null,
      dom: null,
    });
  });
});

describe("buildArtifact", () => {
  it("ensambla el artefacto con source=playwright y mapea los tests", () => {
    const a = buildArtifact(
      [{ testName: "t", status: "pass", retried: false, dom: "<html></html>" }],
      { project: "demo", orgId: "org-1", commitSha: "abc" },
    );
    expect(a.project).toBe("demo");
    expect(a.org_id).toBe("org-1");
    expect(a.commit_sha).toBe("abc");
    expect(a.source).toBe("playwright");
    expect(a.tests).toHaveLength(1);
    expect(a.tests[0].dom).toBe("<html></html>");
  });
});
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/artifact.test.ts`
Expected: FAIL — `Failed to resolve import "../src/artifact"`.

- [ ] **Step 3: Implementar**

`src/artifact.ts`:
```ts
import { ArtifactMeta, CiRunArtifact, CiTestResult, TestResultInput } from "./types";

export function buildTestResult(input: TestResultInput): CiTestResult {
  return {
    test_name: input.testName,
    status: input.status,
    retried: input.retried,
    error_type: input.errorType ?? null,
    message: input.message ?? null,
    trace: input.trace ?? null,
    file: input.file ?? null,
    line: input.line ?? null,
    dom: input.dom ?? null,
  };
}

export function buildArtifact(results: TestResultInput[], meta: ArtifactMeta): CiRunArtifact {
  return {
    project: meta.project,
    org_id: meta.orgId,
    commit_sha: meta.commitSha,
    source: "playwright",
    tests: results.map(buildTestResult),
  };
}
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/artifact.test.ts`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/mnemo-playwright-reporter/src/artifact.ts packages/mnemo-playwright-reporter/tests/artifact.test.ts
git commit -m "feat(reporter): builder puro del CiRunArtifact"
```

---

### Task 3: Resolución de configuración (pura)

**Files:**
- Create: `packages/mnemo-playwright-reporter/src/config.ts`
- Test: `packages/mnemo-playwright-reporter/tests/config.test.ts`

**Interfaces:**
- Consumes: `MnemoConfig` (`src/types.ts`, Task 1).
- Produces: `MnemoOptions` (interfaz de opciones del reporter); `resolveConfig(env: Record<string,string|undefined>, options?: MnemoOptions) -> MnemoConfig | null` (null si falta cualquier requerido).

- [ ] **Step 1: Escribir los tests**

`tests/config.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { resolveConfig } from "../src/config";

const full = {
  MNEMO_WEBHOOK_URL: "http://x/v2/ci/webhook",
  MNEMO_WEBHOOK_SECRET: "s",
  MNEMO_ORG_ID: "o",
  MNEMO_PROJECT: "p",
  GITHUB_SHA: "abc",
};

describe("resolveConfig", () => {
  it("resuelve desde env completo (commit de GITHUB_SHA)", () => {
    expect(resolveConfig(full)).toEqual({
      url: "http://x/v2/ci/webhook",
      secret: "s",
      orgId: "o",
      project: "p",
      commitSha: "abc",
    });
  });

  it("devuelve null si falta un requerido", () => {
    const { MNEMO_PROJECT, ...partial } = full;
    expect(resolveConfig(partial)).toBeNull();
  });

  it("las opciones tienen prioridad sobre env", () => {
    expect(resolveConfig(full, { project: "override" })?.project).toBe("override");
  });

  it("MNEMO_COMMIT_SHA tiene prioridad sobre GITHUB_SHA", () => {
    expect(resolveConfig({ ...full, MNEMO_COMMIT_SHA: "xyz" })?.commitSha).toBe("xyz");
  });
});
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/config.test.ts`
Expected: FAIL — `Failed to resolve import "../src/config"`.

- [ ] **Step 3: Implementar**

`src/config.ts`:
```ts
import { MnemoConfig } from "./types";

export interface MnemoOptions {
  url?: string;
  secret?: string;
  orgId?: string;
  project?: string;
  commitSha?: string;
}

type Env = Record<string, string | undefined>;

/** Resuelve la config desde opciones (prioridad) y env. Devuelve null si falta algo requerido. */
export function resolveConfig(env: Env, options: MnemoOptions = {}): MnemoConfig | null {
  const url = options.url ?? env.MNEMO_WEBHOOK_URL;
  const secret = options.secret ?? env.MNEMO_WEBHOOK_SECRET;
  const orgId = options.orgId ?? env.MNEMO_ORG_ID;
  const project = options.project ?? env.MNEMO_PROJECT;
  const commitSha = options.commitSha ?? env.MNEMO_COMMIT_SHA ?? env.GITHUB_SHA;
  if (!url || !secret || !orgId || !project || !commitSha) return null;
  return { url, secret, orgId, project, commitSha };
}
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/config.test.ts`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/mnemo-playwright-reporter/src/config.ts packages/mnemo-playwright-reporter/tests/config.test.ts
git commit -m "feat(reporter): resolución de config (env + opciones)"
```

---

### Task 4: Envío del artefacto (I/O, failure-safe)

**Files:**
- Create: `packages/mnemo-playwright-reporter/src/post.ts`
- Test: `packages/mnemo-playwright-reporter/tests/post.test.ts`

**Interfaces:**
- Consumes: `CiRunArtifact`, `MnemoConfig` (`src/types.ts`); `sign` (`src/sign.ts`, Task 1).
- Produces: `postArtifact(config: MnemoConfig, artifact: CiRunArtifact, fetchImpl?) -> Promise<void>` — firma el cuerpo y lo POSTea; **nunca lanza** (warn ante error de red o status !ok).

- [ ] **Step 1: Escribir los tests**

`tests/post.test.ts`:
```ts
import { describe, it, expect, vi } from "vitest";
import { postArtifact } from "../src/post";
import { sign } from "../src/sign";
import { CiRunArtifact, MnemoConfig } from "../src/types";

const config: MnemoConfig = {
  url: "http://x/v2/ci/webhook", secret: "s3cr3t", orgId: "o", project: "p", commitSha: "abc",
};
const artifact: CiRunArtifact = {
  project: "p", org_id: "o", commit_sha: "abc", source: "playwright", tests: [],
};

describe("postArtifact", () => {
  it("firma el cuerpo crudo y lo envía con la cabecera correcta", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    await postArtifact(config, artifact, fetchImpl);
    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("http://x/v2/ci/webhook");
    expect(init.headers["X-Hub-Signature-256"]).toBe(sign(init.body, "s3cr3t"));
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body).org_id).toBe("o");
  });

  it("no lanza si fetch rechaza (failure-safe)", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new Error("network down"));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(postArtifact(config, artifact, fetchImpl)).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("no lanza si el webhook responde !ok (failure-safe)", async () => {
    const fetchImpl = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await expect(postArtifact(config, artifact, fetchImpl)).resolves.toBeUndefined();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/post.test.ts`
Expected: FAIL — `Failed to resolve import "../src/post"`.

- [ ] **Step 3: Implementar**

`src/post.ts`:
```ts
import { sign } from "./sign";
import { CiRunArtifact, MnemoConfig } from "./types";

type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; body: string },
) => Promise<{ ok: boolean; status: number }>;

/** Firma y envía el artefacto. Failure-safe: nunca lanza (un reporter no debe tumbar el CI). */
export async function postArtifact(
  config: MnemoConfig,
  artifact: CiRunArtifact,
  fetchImpl: FetchLike = fetch as unknown as FetchLike,
): Promise<void> {
  try {
    const body = JSON.stringify(artifact);
    const signature = sign(body, config.secret);
    const res = await fetchImpl(config.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hub-Signature-256": signature },
      body,
    });
    if (!res.ok) {
      console.warn(`[mnemo] webhook respondió ${res.status}; artefacto no ingerido`);
    }
  } catch (err) {
    console.warn(`[mnemo] no se pudo enviar el artefacto: ${(err as Error).message}`);
  }
}
```

- [ ] **Step 4: Ejecutar (pasa)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/post.test.ts`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/mnemo-playwright-reporter/src/post.ts packages/mnemo-playwright-reporter/tests/post.test.ts
git commit -m "feat(reporter): envío firmado y failure-safe del artefacto"
```

---

### Task 5: Reporter de Playwright (mapeo + dedup + orquestación)

**Files:**
- Create: `packages/mnemo-playwright-reporter/src/reporter.ts`
- Test: `packages/mnemo-playwright-reporter/tests/reporter.test.ts`

**Interfaces:**
- Consumes: `buildArtifact` (Task 2), `resolveConfig`/`MnemoOptions` (Task 3), `postArtifact` (Task 4), `TestResultInput`/`ArtifactMeta` (Task 1); tipos de `@playwright/test/reporter`.
- Produces: `parseErrorType(message?) -> string|null`; `toTestResultInput(test, result) -> TestResultInput` (mapea estructuras de Playwright); `class MnemoReporter implements Reporter` con `onTestEnd` (dedup por `test.id`, conserva el intento final) y `onEnd` (build + post; no-op si config null). Tipos estructurales exportados `PwTestLike`/`PwResultLike`.

- [ ] **Step 1: Escribir los tests**

`tests/reporter.test.ts`:
```ts
import { describe, it, expect, vi, afterEach } from "vitest";
import { MnemoReporter, parseErrorType, toTestResultInput } from "../src/reporter";

const tcase = (over = {}) => ({
  titlePath: () => ["suite", "name"],
  location: { file: "a.spec.ts", line: 10 },
  ...over,
});

describe("parseErrorType", () => {
  it("extrae el primer token XxxError/Exception", () => {
    expect(parseErrorType("TimeoutError: locator not found")).toBe("TimeoutError");
  });
  it("devuelve null si no hay token o no hay mensaje", () => {
    expect(parseErrorType("algo salió mal")).toBeNull();
    expect(parseErrorType(null)).toBeNull();
  });
});

describe("toTestResultInput", () => {
  it("mapea estados passed/failed/timedOut/skipped", () => {
    expect(toTestResultInput(tcase() as any, { status: "passed", retry: 0 } as any).status).toBe("pass");
    expect(toTestResultInput(tcase() as any, { status: "failed", retry: 0 } as any).status).toBe("fail");
    expect(toTestResultInput(tcase() as any, { status: "timedOut", retry: 0 } as any).status).toBe("fail");
    expect(toTestResultInput(tcase() as any, { status: "skipped", retry: 0 } as any).status).toBe("skipped");
  });
  it("passed con retry>0 -> flaky + retried", () => {
    const r = toTestResultInput(tcase() as any, { status: "passed", retry: 1 } as any);
    expect(r.status).toBe("flaky");
    expect(r.retried).toBe(true);
  });
  it("extrae error_type/message/file/line y el dom del attachment", () => {
    const r = toTestResultInput(tcase() as any, {
      status: "failed",
      retry: 0,
      error: { message: "AssertionError: nope", stack: "at a.spec.ts:10" },
      attachments: [{ name: "mnemo-dom", body: Buffer.from("<html></html>"), contentType: "text/html" }],
    } as any);
    expect(r.errorType).toBe("AssertionError");
    expect(r.message).toBe("AssertionError: nope");
    expect(r.trace).toBe("at a.spec.ts:10");
    expect(r.file).toBe("a.spec.ts");
    expect(r.line).toBe(10);
    expect(r.dom).toBe("<html></html>");
  });
});

describe("MnemoReporter", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("dedup por reintentos: conserva el intento final (flaky) y POSTea una vez", async () => {
    const reporter = new MnemoReporter({
      url: "http://x/v2/ci/webhook", secret: "s", orgId: "o", project: "p", commitSha: "abc",
    });
    const tc: any = { id: "t1", titlePath: () => ["login"], location: { file: "l.ts", line: 1 } };
    reporter.onTestEnd(tc, { status: "failed", retry: 0 } as any);
    reporter.onTestEnd(tc, { status: "passed", retry: 1 } as any);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchMock);
    await reporter.onEnd();
    expect(fetchMock).toHaveBeenCalledOnce();
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.tests).toHaveLength(1);
    expect(body.tests[0].status).toBe("flaky");
    expect(body.tests[0].retried).toBe(true);
  });

  it("no-opera (sin POST) si la config está incompleta", async () => {
    const reporter = new MnemoReporter({}); // sin opciones; el env de test no tiene MNEMO_*
    const tc: any = { id: "t1", titlePath: () => ["x"], location: {} };
    reporter.onTestEnd(tc, { status: "passed", retry: 0 } as any);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await reporter.onEnd();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
```

- [ ] **Step 2: Ejecutar (falla)**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/reporter.test.ts`
Expected: FAIL — `Failed to resolve import "../src/reporter"`.

- [ ] **Step 3: Implementar**

`src/reporter.ts`:
```ts
import type { Reporter, TestCase, TestResult } from "@playwright/test/reporter";
import { buildArtifact } from "./artifact";
import { MnemoOptions, resolveConfig } from "./config";
import { postArtifact } from "./post";
import { ArtifactMeta, TestResultInput } from "./types";

const ERR_RE = /([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Failure|Timeout))/;

/** Best-effort: primer token tipo XxxError del mensaje (espejo de parse_error_type del backend). */
export function parseErrorType(message?: string | null): string | null {
  if (!message) return null;
  const m = message.slice(0, 1000).match(ERR_RE);
  return m ? m[1] : null;
}

/** Subconjunto estructural de Playwright para que el mapeo sea testeable sin runtime. */
export interface PwResultLike {
  status: "passed" | "failed" | "timedOut" | "skipped" | "interrupted";
  retry: number;
  error?: { message?: string; stack?: string };
  attachments?: { name: string; body?: Buffer; contentType: string }[];
}
export interface PwTestLike {
  titlePath(): string[];
  location?: { file?: string; line?: number };
}

function mapStatus(status: PwResultLike["status"]): "pass" | "fail" | "skipped" {
  if (status === "passed") return "pass";
  if (status === "skipped") return "skipped";
  return "fail"; // failed | timedOut | interrupted
}

export function toTestResultInput(test: PwTestLike, result: PwResultLike): TestResultInput {
  const base = mapStatus(result.status);
  const status = base === "pass" && result.retry > 0 ? "flaky" : base;
  const dom =
    result.attachments?.find((a) => a.name === "mnemo-dom")?.body?.toString("utf8") ?? null;
  return {
    testName: test.titlePath().join(" > "),
    status,
    retried: result.retry > 0,
    errorType: parseErrorType(result.error?.message),
    message: result.error?.message ?? null,
    trace: result.error?.stack ?? null,
    file: test.location?.file ?? null,
    line: test.location?.line ?? null,
    dom,
  };
}

export class MnemoReporter implements Reporter {
  private readonly options: MnemoOptions;
  private readonly results = new Map<string, TestResultInput>();
  private readonly seenRetry = new Map<string, number>();

  constructor(options: MnemoOptions = {}) {
    this.options = options;
  }

  onTestEnd(test: TestCase, result: TestResult): void {
    const id = test.id;
    const prev = this.seenRetry.get(id);
    if (prev !== undefined && result.retry < prev) return; // conserva el intento final
    this.seenRetry.set(id, result.retry);
    this.results.set(
      id,
      toTestResultInput(test as unknown as PwTestLike, result as unknown as PwResultLike),
    );
  }

  async onEnd(): Promise<void> {
    const config = resolveConfig(process.env, this.options);
    if (!config) {
      console.warn("[mnemo] config incompleta (url/secret/org/project/commit); no se envía nada");
      return;
    }
    const meta: ArtifactMeta = {
      project: config.project,
      orgId: config.orgId,
      commitSha: config.commitSha,
    };
    await postArtifact(config, buildArtifact([...this.results.values()], meta));
  }
}
```

- [ ] **Step 4: Ejecutar (pasa) + typecheck**

Run: `cd packages/mnemo-playwright-reporter && npx vitest run tests/reporter.test.ts && npx tsc --noEmit`
Expected: tests PASS; tsc sin errores.

- [ ] **Step 5: Commit**

```bash
git add packages/mnemo-playwright-reporter/src/reporter.ts packages/mnemo-playwright-reporter/tests/reporter.test.ts
git commit -m "feat(reporter): MnemoReporter (mapeo Playwright + dedup + onEnd)"
```

---

### Task 6: Fixture de captura DOM + exports + README + verificación final

**Files:**
- Create: `packages/mnemo-playwright-reporter/src/fixture.ts`
- Create: `packages/mnemo-playwright-reporter/src/index.ts`
- Create: `packages/mnemo-playwright-reporter/README.md`

**Interfaces:**
- Consumes: `@playwright/test` (runtime); `MnemoReporter` (Task 5); tipos (Task 1).
- Produces: `test` (auto-fixture que adjunta `mnemo-dom`) y `expect` re-exportados (`src/fixture.ts`); `index.ts` con `export default MnemoReporter`, `export { test, expect }`, y re-export de tipos del contrato.

> El fixture usa el runtime de Playwright (captura DOM real), que no se testea unitariamente aquí — se valida en la demo e2e (F6). La verificación de esta tarea es typecheck + build + suite vitest completa verde.

- [ ] **Step 1: Implementar el fixture**

`src/fixture.ts`:
```ts
import { test as base } from "@playwright/test";

/** Auto-fixture: tras cada test captura el DOM de la página y lo adjunta para el reporter. */
export const test = base.extend<{ mnemoDom: void }>({
  mnemoDom: [
    async ({ page }, use, testInfo) => {
      await use();
      try {
        const html = await page.content();
        await testInfo.attach("mnemo-dom", { body: Buffer.from(html), contentType: "text/html" });
      } catch {
        // No romper el test si la página ya no está disponible.
      }
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
```

- [ ] **Step 2: Implementar los exports**

`src/index.ts`:
```ts
export { MnemoReporter as default } from "./reporter";
export { test, expect } from "./fixture";
export type { CiRunArtifact, CiTestResult, MnemoConfig } from "./types";
```

- [ ] **Step 3: Escribir el README**

`README.md`:
````markdown
# mnemo-playwright-reporter

Reporter + auto-fixture de Playwright que envía los resultados de cada run (estado,
reintentos, error y **DOM** por test) a Mnemo Autopilot (`POST /v2/ci/webhook`),
firmados con HMAC. Convierte la ingesta de QA en "viva desde el CI".

## Instalación

```bash
npm install -D mnemo-playwright-reporter
npm run build   # genera dist/ (el paquete se consume compilado)
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
````

- [ ] **Step 4: Verificación final (typecheck + build + suite completa)**

Run: `cd packages/mnemo-playwright-reporter && npx tsc --noEmit && npm run build && npm test`
Expected: tsc sin errores; `dist/` generado con `.d.ts`; **toda** la suite vitest verde (sign, artifact, config, post, reporter).

- [ ] **Step 5: Commit**

```bash
git add packages/mnemo-playwright-reporter/src/fixture.ts packages/mnemo-playwright-reporter/src/index.ts packages/mnemo-playwright-reporter/README.md
git commit -m "feat(reporter): fixture de captura DOM + exports + README"
```

---

## Self-Review

**1. Cobertura del spec:**
- Contrato (tipos snake_case) → Task 1 (`types.ts`). ✓
- Firma HMAC byte-compatible + test de interop con Python → Task 1 (`sign.ts`, `sign.test.ts`). ✓
- Builder del artefacto (pure) → Task 2. ✓
- Config env+opciones, null si incompleta → Task 3. ✓
- Envío failure-safe → Task 4. ✓
- Mapeo Playwright→contrato + dedup reintentos + flaky/retried + onEnd → Task 5. ✓
- Captura DOM (fixture) → Task 6. ✓
- Exports (default reporter + `test`) y README → Task 6. ✓
- Packaging (tsconfig CJS, build dist, vitest) → Task 1 + Task 6. ✓

**2. Placeholders:** ninguno; todo paso de código lleva el código completo y cada comando su salida esperada. El vector HMAC está fijado a un valor real verificado (Python==Node).

**3. Consistencia de tipos:** `TestResultInput` (camelCase) producido en Task 1 y consumido por `buildTestResult` (Task 2) y `toTestResultInput` (Task 5); `MnemoConfig`/`resolveConfig` (Task 3) consumidos por `postArtifact` (Task 4) y `MnemoReporter.onEnd` (Task 5); `sign` (Task 1) usado por `post` (Task 4) y los tests; `buildArtifact` (Task 2) usado por el reporter (Task 5). `source` siempre `"playwright"`.

**Nota de entorno:** el test "no-opera si config incompleta" (Task 5) asume que el entorno de ejecución de vitest no define las `MNEMO_*` (cierto para el CI de este paquete; `GITHUB_SHA` por sí solo no basta porque faltan url/secret/org/project).

---

## Handoff de ejecución

Plan completo y guardado en `docs/superpowers/plans/2026-06-22-mnemo-autopilot-f1b-reporter.md`. Dos opciones:

1. **Subagent-Driven (recomendada)** — un subagente fresco por tarea, revisión entre tareas, iteración rápida.
2. **Inline Execution** — ejecutar en esta sesión con checkpoints por lotes.

> Nota: este paquete necesita `npm install` (descarga `@playwright/test`, `typescript`, `vitest`) en `packages/mnemo-playwright-reporter/` durante la Task 1. El resto de tareas reutiliza esa instalación.
