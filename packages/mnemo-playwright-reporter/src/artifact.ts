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
