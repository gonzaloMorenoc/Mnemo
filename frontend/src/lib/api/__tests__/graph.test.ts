import { afterEach, describe, expect, it, vi } from "vitest";

import { getGaps, getGraph } from "@/lib/api/endpoints";
import type { CoverageGap, Graph } from "@/lib/api/types";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

const GRAPH: Graph = {
  nodes: [
    { id: "n1", type: "knowledge", label: "Auth flows", kind: "lesson" },
    { id: "n2", type: "domain", label: "Payments", count: 3 },
  ],
  edges: [{ source: "n1", target: "n2", relation: "pertenece" }],
};

const GAPS: CoverageGap[] = [
  {
    kind: "lesson",
    title: "No flaky test coverage",
    severity: "alta",
    affected: ["n1"],
    recommendation: "Add retry logic tests",
  },
];

describe("getGraph", () => {
  it("GETs /api/v2/graph?org_id=... and parses {nodes,edges}", async () => {
    const spy = mockFetch(GRAPH);

    const res = await getGraph("tok", { org_id: "org-1" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph?org_id=org-1");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res.nodes).toHaveLength(2);
    expect(res.edges).toHaveLength(1);
    expect(res.nodes[0].id).toBe("n1");
  });

  it("appends focus when provided", async () => {
    const spy = mockFetch(GRAPH);

    await getGraph("tok", { org_id: "org-1", focus: "auth" });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph?org_id=org-1&focus=auth");
  });

  it("appends limit when provided", async () => {
    const spy = mockFetch(GRAPH);

    await getGraph("tok", { org_id: "org-1", limit: 50 });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph?org_id=org-1&limit=50");
  });

  it("appends both focus and limit when provided", async () => {
    const spy = mockFetch(GRAPH);

    await getGraph("tok", { org_id: "org-1", focus: "payments", limit: 20 });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph?org_id=org-1&focus=payments&limit=20");
  });
});

describe("getGaps", () => {
  it("GETs /api/v2/graph/gaps?org_id=... and parses the array", async () => {
    const spy = mockFetch(GAPS);

    const res = await getGaps("tok", { org_id: "org-1" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph/gaps?org_id=org-1");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res).toHaveLength(1);
    expect(res[0].kind).toBe("lesson");
    expect(res[0].severity).toBe("alta");
    expect(res[0].affected).toEqual(["n1"]);
  });

  it("URL-encodes org_id with special characters", async () => {
    const spy = mockFetch(GAPS);

    await getGaps("tok", { org_id: "org/with spaces" });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph/gaps?org_id=org%2Fwith%20spaces");
  });

  it("appends recommendations=false to skip the LLM (dashboard count-only)", async () => {
    const spy = mockFetch(GAPS);

    await getGaps("tok", { org_id: "org-1", recommendations: false });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph/gaps?org_id=org-1&recommendations=false");
  });

  it("does NOT append recommendations by default (graph page needs them)", async () => {
    const spy = mockFetch(GAPS);

    await getGaps("tok", { org_id: "org-1" });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/graph/gaps?org_id=org-1");
  });
});
