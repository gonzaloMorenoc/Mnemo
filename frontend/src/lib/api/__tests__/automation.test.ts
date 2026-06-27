import { afterEach, describe, expect, it, vi } from "vitest";

import { generatePlaywrightTest, openAutomationPr } from "@/lib/api/endpoints";
import type { TestCase } from "@/lib/api/types";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

const TEST_CASE: TestCase = {
  title: "User can add item to cart",
  level: "e2e",
  priority: "high",
  automatable: true,
  steps: ["Navigate to product page", "Click 'Add to cart'"],
  expected: "Cart count increments by 1",
};

const GENERATED_TEST = {
  code: "import { test, expect } from '@playwright/test';\ntest('add item to cart', ...) {}",
  filename: "cart.spec.ts",
  notes: "Uses page object model",
};

const PR_RESPONSE = {
  pr_url: "https://github.com/org/repo/pull/42",
};

describe("generatePlaywrightTest", () => {
  it("POSTs to /api/v2/automation/generate with JSON body and auth header", async () => {
    const spy = mockFetch(GENERATED_TEST);

    await generatePlaywrightTest("tok", { case: TEST_CASE });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/automation/generate");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers((init as RequestInit).headers).get("Content-Type")).toBe("application/json");
  });

  it("serialises the case in the JSON body", async () => {
    const spy = mockFetch(GENERATED_TEST);

    await generatePlaywrightTest("tok", { case: TEST_CASE });

    const [, init] = spy.mock.calls[0];
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.case.title).toBe("User can add item to cart");
    expect(sent.case.priority).toBe("high");
    expect(sent.case.automatable).toBe(true);
  });

  it("includes optional style_sample when provided", async () => {
    const spy = mockFetch(GENERATED_TEST);

    await generatePlaywrightTest("tok", { case: TEST_CASE, style_sample: "// my style" });

    const [, init] = spy.mock.calls[0];
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.style_sample).toBe("// my style");
  });

  it("returns parsed GeneratedTest with code, filename, and notes", async () => {
    mockFetch(GENERATED_TEST);

    const result = await generatePlaywrightTest("tok", { case: TEST_CASE });

    expect(result.code).toContain("@playwright/test");
    expect(result.filename).toBe("cart.spec.ts");
    expect(result.notes).toBe("Uses page object model");
  });
});

describe("openAutomationPr", () => {
  it("POSTs to /api/v2/automation/pr with JSON body and auth header", async () => {
    const spy = mockFetch(PR_RESPONSE);

    await openAutomationPr("tok", {
      org_id: "org-1",
      code: GENERATED_TEST.code,
      filename: GENERATED_TEST.filename,
    });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/automation/pr");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers((init as RequestInit).headers).get("Content-Type")).toBe("application/json");
  });

  it("serialises org_id, code, and filename in the body", async () => {
    const spy = mockFetch(PR_RESPONSE);

    await openAutomationPr("tok", {
      org_id: "org-1",
      code: GENERATED_TEST.code,
      filename: GENERATED_TEST.filename,
    });

    const [, init] = spy.mock.calls[0];
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.org_id).toBe("org-1");
    expect(sent.code).toBe(GENERATED_TEST.code);
    expect(sent.filename).toBe("cart.spec.ts");
  });

  it("includes optional title when provided", async () => {
    const spy = mockFetch(PR_RESPONSE);

    await openAutomationPr("tok", {
      org_id: "org-1",
      code: GENERATED_TEST.code,
      filename: GENERATED_TEST.filename,
      title: "test: add cart automation",
    });

    const [, init] = spy.mock.calls[0];
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.title).toBe("test: add cart automation");
  });

  it("returns parsed response with pr_url", async () => {
    mockFetch(PR_RESPONSE);

    const result = await openAutomationPr("tok", {
      org_id: "org-1",
      code: GENERATED_TEST.code,
      filename: GENERATED_TEST.filename,
    });

    expect(result.pr_url).toBe("https://github.com/org/repo/pull/42");
  });
});
