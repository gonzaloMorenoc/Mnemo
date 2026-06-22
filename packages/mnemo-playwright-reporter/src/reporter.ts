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
