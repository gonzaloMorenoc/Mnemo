import { afterEach, describe, expect, it, vi } from "vitest";

import { getDefects, getAssuranceVerdict } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

describe("mnemo endpoints", () => {
  it("getDefects calls /api/v2/defects with org_id query and bearer token", async () => {
    const spy = mockFetch([{ id: "f1", title: "T", status: "open", occurrence_count: 2, projects: [] }]);
    const out = await getDefects("tok", "org-1");
    expect(out[0].id).toBe("f1");
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/defects?org_id=org-1");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
  });

  it("getAssuranceVerdict calls /api/v2/assurance/run/{id}", async () => {
    mockFetch({ run_id: "r1", ingested: 1, known: 0, novel: 1, risk: "atencion", top_families: [], narrative: null });
    const out = await getAssuranceVerdict("tok", "r1");
    expect(out.run_id).toBe("r1");
    expect(out.risk).toBe("atencion");
  });
});
