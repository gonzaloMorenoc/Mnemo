import { afterEach, describe, expect, it, vi } from "vitest";

import { domainSummary, learningPath } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

const DOMAIN_SUMMARY = {
  rules: ["rule-1"],
  systems: ["auth-service"],
  existing_tests: ["login.spec.ts"],
  historical_bugs: ["BUG-42"],
  risks: ["session expiry"],
  citations: ["k1"],
};

const LEARNING_PATH = {
  days: [
    { day: 1, items: ["Read onboarding guide"] },
    { day: 2, items: ["Run smoke tests"] },
  ],
  citations: ["k2"],
};

describe("domainSummary", () => {
  it("POSTs to /api/v2/onboarding/domain-summary with JSON body and auth header", async () => {
    const spy = mockFetch(DOMAIN_SUMMARY);

    await domainSummary("tok", { org_id: "o1", topic: "auth" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/onboarding/domain-summary");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers((init as RequestInit).headers).get("Content-Type")).toBe("application/json");
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.org_id).toBe("o1");
    expect(sent.topic).toBe("auth");
  });

  it("returns a parsed DomainSummary", async () => {
    mockFetch(DOMAIN_SUMMARY);

    const res = await domainSummary("tok", { org_id: "o1", topic: "auth" });

    expect(res.rules).toEqual(["rule-1"]);
    expect(res.systems).toEqual(["auth-service"]);
    expect(res.existing_tests).toEqual(["login.spec.ts"]);
    expect(res.historical_bugs).toEqual(["BUG-42"]);
    expect(res.risks).toEqual(["session expiry"]);
    expect(res.citations).toEqual(["k1"]);
  });
});

describe("learningPath", () => {
  it("POSTs to /api/v2/onboarding/learning-path with JSON body and auth header", async () => {
    const spy = mockFetch(LEARNING_PATH);

    await learningPath("tok", { org_id: "o1", topic: "auth" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/onboarding/learning-path");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers((init as RequestInit).headers).get("Content-Type")).toBe("application/json");
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.org_id).toBe("o1");
    expect(sent.topic).toBe("auth");
  });

  it("returns a parsed LearningPath with days and citations", async () => {
    mockFetch(LEARNING_PATH);

    const res = await learningPath("tok", { org_id: "o1", topic: "auth" });

    expect(res.days).toHaveLength(2);
    expect(res.days[0].day).toBe(1);
    expect(res.days[0].items).toEqual(["Read onboarding guide"]);
    expect(res.days[1].day).toBe(2);
    expect(res.citations).toEqual(["k2"]);
  });
});
