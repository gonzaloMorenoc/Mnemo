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
      runUid: null,
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

describe("resolveConfig · runUid (dedup del backend)", () => {
  it("MNEMO_RUN_UID tiene prioridad máxima", () => {
    expect(
      resolveConfig({ ...full, MNEMO_RUN_UID: "custom-1", GITHUB_RUN_ID: "99" })?.runUid,
    ).toBe("custom-1");
  });

  it("deriva de GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT (re-run del job = mismo run_uid → dedup)", () => {
    expect(
      resolveConfig({ ...full, GITHUB_RUN_ID: "12345", GITHUB_RUN_ATTEMPT: "2" })?.runUid,
    ).toBe("gh-12345-2");
  });

  it("GITHUB_RUN_ATTEMPT ausente asume intento 1", () => {
    expect(resolveConfig({ ...full, GITHUB_RUN_ID: "12345" })?.runUid).toBe("gh-12345-1");
  });

  it("sin fuentes queda null (retrocompatible: el backend no deduplica)", () => {
    expect(resolveConfig(full)?.runUid).toBeNull();
  });

  it("la opción programática gana a todo", () => {
    expect(
      resolveConfig({ ...full, MNEMO_RUN_UID: "env" }, { runUid: "opt" })?.runUid,
    ).toBe("opt");
  });
});
