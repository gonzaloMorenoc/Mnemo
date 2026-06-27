import { afterEach, describe, expect, it, vi } from "vitest";

import { exportTestPlanXray, generateTestPlan } from "@/lib/api/endpoints";
import type { TestPlan } from "@/lib/api/types";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

const PLAN: TestPlan = {
  summary: "QA plan for checkout",
  systems: ["web", "api"],
  risks: ["payment failure"],
  preconditions: ["user logged in"],
  test_data: ["card 4242424242424242"],
  cases: [
    {
      title: "Happy path checkout",
      level: "integration",
      priority: "high",
      automatable: true,
      steps: ["add item to cart", "checkout"],
      expected: "order confirmed",
    },
  ],
  gaps: ["no mobile coverage"],
  open_questions: ["what about 3DS?"],
  citations: ["HU-42"],
};

const PLAN_RESULT = { plan: PLAN, citations: ["HU-42"] };

describe("generateTestPlan", () => {
  it("POSTs the FormData to /api/v2/test-plan/generate with bearer token", async () => {
    const spy = mockFetch(PLAN_RESULT);
    const form = new FormData();
    form.append("org_id", "org-1");
    form.append("case_format", "steps");

    const result = await generateTestPlan("tok", form);

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/test-plan/generate");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect((init as RequestInit).body).toBe(form);
    expect(result.plan.summary).toBe("QA plan for checkout");
    expect(result.citations).toEqual(["HU-42"]);
  });

  it("does NOT set Content-Type (browser sets multipart boundary)", async () => {
    const spy = mockFetch(PLAN_RESULT);
    const form = new FormData();
    form.append("org_id", "org-1");
    form.append("case_format", "steps");

    await generateTestPlan("tok", form);

    const [, init] = spy.mock.calls[0];
    expect(new Headers((init as RequestInit).headers).get("Content-Type")).toBeNull();
  });

  it("returns parsed TestPlanResult", async () => {
    mockFetch(PLAN_RESULT);
    const form = new FormData();

    const result = await generateTestPlan("tok", form);

    expect(result.plan.cases).toHaveLength(1);
    expect(result.plan.cases[0].title).toBe("Happy path checkout");
    expect(result.plan.cases[0].automatable).toBe(true);
  });
});

describe("exportTestPlanXray", () => {
  it("POSTs JSON body to /api/v2/test-plan/export/xray with bearer token", async () => {
    const xrayKeys = { "TC-1": "XR-10001" };
    const spy = mockFetch(xrayKeys);

    const result = await exportTestPlanXray("tok", {
      org_id: "org-1",
      plan: PLAN,
      case_format: "steps",
    });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/test-plan/export/xray");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers((init as RequestInit).headers).get("Content-Type")).toBe("application/json");
    expect(result).toEqual(xrayKeys);
  });

  it("serialises the body including plan and case_format", async () => {
    const spy = mockFetch({});

    await exportTestPlanXray("tok", {
      org_id: "org-99",
      plan: PLAN,
      case_format: "gherkin",
    });

    const [, init] = spy.mock.calls[0];
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.org_id).toBe("org-99");
    expect(sent.case_format).toBe("gherkin");
    expect(sent.plan.summary).toBe("QA plan for checkout");
  });
});
