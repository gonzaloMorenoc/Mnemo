import { afterEach, describe, expect, it, vi } from "vitest";

import { indexRepo, listRepoTests } from "@/lib/api/endpoints";
import type { RepoIndexResult, TestAsset } from "@/lib/api/types";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

const INDEX_RESULT: RepoIndexResult = {
  indexed: 42,
  by_domain: { auth: 10, payments: 32 },
  skipped: 3,
};

const TEST_ASSETS: TestAsset[] = [
  { path: "tests/auth/login.spec.ts", framework: "playwright", domain: "auth" },
  { path: "tests/payments/checkout.spec.ts", framework: "playwright", domain: "payments" },
];

describe("indexRepo", () => {
  it("POSTs to /api/v2/repo/index with org_id body and parses {indexed,by_domain,skipped}", async () => {
    const spy = mockFetch(INDEX_RESULT);

    const res = await indexRepo("tok", { org_id: "org-1" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/repo/index");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    const sent = JSON.parse((init as RequestInit).body as string);
    expect(sent.org_id).toBe("org-1");
    expect(res.indexed).toBe(42);
    expect(res.by_domain).toEqual({ auth: 10, payments: 32 });
    expect(res.skipped).toBe(3);
  });

  it("includes Authorization header with the token", async () => {
    const spy = mockFetch(INDEX_RESULT);

    await indexRepo("my-secret-token", { org_id: "org-2" });

    const [, init] = spy.mock.calls[0];
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe(
      "Bearer my-secret-token",
    );
  });
});

describe("listRepoTests", () => {
  it("GETs /api/v2/repo/tests?org_id=... and parses the TestAsset array", async () => {
    const spy = mockFetch(TEST_ASSETS);

    const res = await listRepoTests("tok", { org_id: "org-1" });

    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/repo/tests?org_id=org-1");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).get("Authorization")).toBe("Bearer tok");
    expect(res).toHaveLength(2);
    expect(res[0].path).toBe("tests/auth/login.spec.ts");
    expect(res[0].framework).toBe("playwright");
    expect(res[0].domain).toBe("auth");
  });

  it("URL-encodes org_id with special characters", async () => {
    const spy = mockFetch(TEST_ASSETS);

    await listRepoTests("tok", { org_id: "org/with spaces" });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/repo/tests?org_id=org%2Fwith%20spaces");
  });

  it("returns an empty array when no tests exist", async () => {
    const spy = mockFetch([]);

    const res = await listRepoTests("tok", { org_id: "org-empty" });

    const [url] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/repo/tests?org_id=org-empty");
    expect(res).toHaveLength(0);
  });
});
