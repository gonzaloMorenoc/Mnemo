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
