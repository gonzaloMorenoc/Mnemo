import { afterEach, describe, expect, it, vi } from "vitest";

import { getCalibrationMetrics, setFamilyLabel } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok, status, text: async () => JSON.stringify(json),
  } as unknown as Response);
}

function lastCall(spy: ReturnType<typeof mockFetch>) {
  const [url, init] = spy.mock.calls[0];
  return { url: String(url), init: init as RequestInit };
}

describe("foso endpoints", () => {
  it("getCalibrationMetrics → GET /api/v2/calibration/metrics?org_id= con bearer", async () => {
    const spy = mockFetch({ total: 3, aciertos: 2, accuracy: 0.6667, familias_calibradas: 2, por_categoria: { flaky: 2, real: 1 } });
    const out = await getCalibrationMetrics("tok", "org-1");
    expect(out.familias_calibradas).toBe(2);
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/calibration/metrics?org_id=org-1");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("setFamilyLabel → PATCH /api/v2/defects/{id}/label con body {label, reason}", async () => {
    const spy = mockFetch({ family_id: "fam-1", label: "flaky" });
    const out = await setFamilyLabel("tok", "fam-1", "flaky", "histórico flaky");
    expect(out.label).toBe("flaky");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/defects/fam-1/label");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ label: "flaky", reason: "histórico flaky" });
  });

  it("setFamilyLabel envía reason vacío por defecto", async () => {
    const spy = mockFetch({ family_id: "fam-1", label: "real" });
    await setFamilyLabel("tok", "fam-1", "real");
    expect(JSON.parse(lastCall(spy).init.body as string)).toEqual({ label: "real", reason: "" });
  });
});
