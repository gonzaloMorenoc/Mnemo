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
