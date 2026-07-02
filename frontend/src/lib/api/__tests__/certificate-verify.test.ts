import { afterEach, describe, expect, it, vi } from "vitest";

import { getCertificatePubkey, verifyCertificate } from "@/lib/api/endpoints";

afterEach(() => vi.restoreAllMocks());

function mockFetch(json: unknown, ok = true, status = 200) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok,
    status,
    text: async () => JSON.stringify(json),
  } as unknown as Response);
}

describe("endpoints públicos de verificación de certificados", () => {
  it("verifyCertificate hace POST a /api/v2/certificates/verify SIN Authorization", async () => {
    const spy = mockFetch({ valido: true });
    const out = await verifyCertificate({ canonical_json: { schema: "mnemo.cert.v2" }, signature: "sig" });
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/certificates/verify");
    expect((init as RequestInit).method).toBe("POST");
    expect(new Headers((init as RequestInit).headers).has("Authorization")).toBe(false);
    expect(out.valido).toBe(true);
  });

  it("getCertificatePubkey hace GET a /api/v2/certificates/pubkey SIN Authorization", async () => {
    const spy = mockFetch({ algorithm: "ed25519", public_key_pem: "-----BEGIN PUBLIC KEY-----" });
    const out = await getCertificatePubkey();
    const [url, init] = spy.mock.calls[0];
    expect(String(url)).toBe("/api/v2/certificates/pubkey");
    expect((init as RequestInit).method).toBe("GET");
    expect(new Headers((init as RequestInit).headers).has("Authorization")).toBe(false);
    expect(out.algorithm).toBe("ed25519");
  });
});
