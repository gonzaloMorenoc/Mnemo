import { afterEach, describe, expect, it, vi } from "vitest";

import {
  askKnowledge,
  createKnowledge,
  listKnowledge,
  searchKnowledge,
} from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

const ITEM = {
  id: "k1",
  kind: "lesson",
  title: "T",
  tags: [],
  confidence: "high",
  created_at: "2026-01-01T00:00:00Z",
};

describe("createKnowledge", () => {
  it("POSTs to /api/v2/knowledge with the body", async () => {
    const spy = mockFetch(ITEM);

    const res = await createKnowledge("tok", { kind: "lesson", title: "T", org_id: "o1" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/knowledge");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res.id).toBe("k1");
  });
});

describe("listKnowledge", () => {
  it("GETs /api/v2/knowledge?org_id=... without kind", async () => {
    const spy = mockFetch([ITEM]);

    const res = await listKnowledge("tok", "org-42");

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/knowledge?org_id=org-42");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("k1");
  });

  it("appends kind when provided", async () => {
    const spy = mockFetch([ITEM]);

    await listKnowledge("tok", "org-42", "lesson");

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/knowledge?org_id=org-42&kind=lesson");
  });
});

describe("searchKnowledge", () => {
  it("POSTs to /api/v2/knowledge/search and returns KnowledgeSource[]", async () => {
    const sources = [{ id: "s1", type: "knowledge" as const, content: "ctx" }];
    const spy = mockFetch(sources);

    const res = await searchKnowledge("tok", { org_id: "o1", query: "flaky tests" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/knowledge/search");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res[0].id).toBe("s1");
    expect(res[0].type).toBe("knowledge");
  });

  it("forwards the k parameter in the body", async () => {
    const spy = mockFetch([]);

    await searchKnowledge("tok", { org_id: "o1", query: "q", k: 5 });

    const [, init] = spy.mock.calls[0];
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.k).toBe(5);
  });
});

describe("askKnowledge", () => {
  it("POSTs to /api/v2/knowledge/ask and returns KnowledgeAnswer", async () => {
    const answer = { answer: "42", citations: ["k1"] };
    const spy = mockFetch(answer);

    const res = await askKnowledge("tok", { org_id: "o1", question: "why?" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/knowledge/ask");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res.answer).toBe("42");
    expect(res.citations).toEqual(["k1"]);
  });
});
