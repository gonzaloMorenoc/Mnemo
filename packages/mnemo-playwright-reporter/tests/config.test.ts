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
