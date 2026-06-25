import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getTriageVerdicts, proposeActions, getActions, approveAction, rejectAction,
  generateCertificate, getCertificate, publishGate,
} from "@/lib/api/endpoints";

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

describe("autopilot endpoints", () => {
  it("getTriageVerdicts → GET /api/v2/triage/run/{id} con bearer", async () => {
    const spy = mockFetch([{ id: "v1", failure_id: "f1", category: "real", confidence: 0.85,
      rule_applied: "R4_real_recurrent", requires_approval: false, llm_assisted: false, status: "resolved" }]);
    const out = await getTriageVerdicts("tok", "r1");
    expect(out[0].category).toBe("real");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/triage/run/r1");
    expect(init.method).toBe("GET");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("proposeActions → POST /api/v2/actions/run/{id}/propose", async () => {
    const spy = mockFetch({ quarantine: 1, ticket: 0, self_heal: 0, skipped: 0 });
    await proposeActions("tok", "r1");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/actions/run/r1/propose");
    expect(init.method).toBe("POST");
  });

  it("getActions → GET /api/v2/actions con org_id (y status opcional)", async () => {
    const spy = mockFetch([]);
    await getActions("tok", "org-1", "proposed");
    expect(lastCall(spy).url).toBe("/api/v2/actions?org_id=org-1&status=proposed");
  });

  it("approveAction → POST /api/v2/actions/{id}/approve", async () => {
    const spy = mockFetch({ approved: true, materialized: true, artifact_ref: "https://x" });
    const out = await approveAction("tok", "a1");
    expect(out.materialized).toBe(true);
    expect(lastCall(spy).url).toBe("/api/v2/actions/a1/approve");
  });

  it("rejectAction → POST /api/v2/actions/{id}/reject con reason en el body", async () => {
    const spy = mockFetch({ rejected: true });
    await rejectAction("tok", "a1", "falso positivo");
    const { url, init } = lastCall(spy);
    expect(url).toBe("/api/v2/actions/a1/reject");
    expect(JSON.parse(init.body as string)).toEqual({ reason: "falso positivo" });
  });

  it("generateCertificate → POST; getCertificate → GET /api/v2/certificates/{id}", async () => {
    const spy = mockFetch({ run_id: "r1", verdict: "apto", risk_score: 0, canonical_json: {}, signature: "s" });
    await generateCertificate("tok", "r1");
    expect(lastCall(spy).url).toBe("/api/v2/certificates/run/r1");
    spy.mockClear();
    await getCertificate("tok", "r1");
    expect(lastCall(spy).url).toBe("/api/v2/certificates/r1");
  });

  it("publishGate → POST /api/v2/gate/run/{id}", async () => {
    const spy = mockFetch({ verdict: "no-apto", conclusion: "failure", check_run_url: "https://x" });
    const out = await publishGate("tok", "r1");
    expect(out.conclusion).toBe("failure");
    expect(lastCall(spy).url).toBe("/api/v2/gate/run/r1");
  });
});
