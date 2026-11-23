import { afterEach, describe, expect, it, vi } from "vitest";

import { getLlmSettings, putLlmSettings } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

const SETTINGS = {
  org_id: "org-1",
  allow_external_llm: false,
  provider: "openai",
  provider_is_external: true,
  global_external_allowed: true,
};

function mockFetch(json: unknown) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

describe("llm-settings", () => {
  it("GET lee el ajuste de la org", async () => {
    const spy = mockFetch(SETTINGS);
    const res = await getLlmSettings("tok", "org-1");
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/orgs/org-1/llm-settings");
    expect((init as RequestInit).method).toBe("GET");
    expect(res.allow_external_llm).toBe(false);
  });

  it("PUT manda allow_external_llm", async () => {
    const spy = mockFetch(SETTINGS);
    await putLlmSettings("tok", "org-1", false);
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/orgs/org-1/llm-settings");
    expect((init as RequestInit).method).toBe("PUT");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ allow_external_llm: false });
  });
});
