import { afterEach, describe, expect, it, vi } from "vitest";

import { getBriefing } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok, status, text: async () => JSON.stringify(json),
  } as unknown as Response);
}

describe("getBriefing", () => {
  it("calls the briefing endpoint for the run", async () => {
    const payload = {
      verdict: "apto",
      summary: "s",
      recommendation: "r",
      highlights: [],
      citations: [],
    };
    const spy = mockFetch(payload);

    const res = await getBriefing("tok", "r1");

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/runs/r1/briefing");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res.verdict).toBe("apto");
  });

  it("URL-encodes runId special characters", async () => {
    const payload = {
      verdict: "no-apto",
      summary: "s",
      recommendation: "r",
      highlights: ["h1"],
      citations: ["c1"],
    };
    const spy = mockFetch(payload);

    await getBriefing("tok", "run/with spaces");

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/runs/run%2Fwith%20spaces/briefing");
  });
});
