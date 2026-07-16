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

  it("incluye run_uid cuando la meta lo trae (idempotencia del webhook)", () => {
    const a = buildArtifact([], { project: "demo", orgId: "o", commitSha: "abc", runUid: "gh-1-1" });
    expect(a.run_uid).toBe("gh-1-1");
  });

  it("run_uid queda null si la meta no lo trae (retrocompatible)", () => {
    const a = buildArtifact([], { project: "demo", orgId: "o", commitSha: "abc" });
    expect(a.run_uid).toBeNull();
  });
});
