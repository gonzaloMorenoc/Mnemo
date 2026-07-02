import type { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/env", () => ({
  getPublicEnv: vi.fn(() => ({ supabaseUrl: "", supabaseAnonKey: "", apiBaseUrl: "http://backend" })),
}));

import { getPublicEnv } from "@/lib/env";
import { proxyToBackend } from "@/lib/server/proxy";

const mockedEnv = vi.mocked(getPublicEnv);

function req(): NextRequest {
  return { headers: new Headers() } as unknown as NextRequest;
}

function setBase(apiBaseUrl: string) {
  mockedEnv.mockReturnValue({ supabaseUrl: "", supabaseAnonKey: "", apiBaseUrl });
}

describe("proxyToBackend", () => {
  it("500 cuando NEXT_PUBLIC_API_BASE_URL no está configurada", async () => {
    setBase("");
    const res = await proxyToBackend(req(), "/v2/orgs", { method: "GET" });
    expect(res.status).toBe(500);
  });

  it("504 con mensaje claro cuando el backend expira (no cuelga hasta maxDuration)", async () => {
    setBase("http://backend");
    vi.spyOn(global, "fetch").mockRejectedValue(
      new DOMException("The operation timed out", "TimeoutError"),
    );
    const res = await proxyToBackend(req(), "/v2/orgs", { method: "GET" });
    expect(res.status).toBe(504);
    const body = (await res.json()) as { detail: string };
    expect(body.detail).toMatch(/iniciándose|Reinténtalo/);
  });

  it("502 cuando el backend es inalcanzable", async () => {
    setBase("http://backend");
    vi.spyOn(global, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const res = await proxyToBackend(req(), "/v2/orgs", { method: "GET" });
    expect(res.status).toBe(502);
  });

  it("reenvía status y cuerpo del backend, pasando un AbortSignal al fetch", async () => {
    setBase("http://backend");
    const spy = vi.spyOn(global, "fetch").mockResolvedValue({
      status: 200,
      text: async () => JSON.stringify([{ id: "o1" }]),
    } as unknown as Response);
    const res = await proxyToBackend(req(), "/v2/orgs", { method: "GET" });
    expect(res.status).toBe(200);
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});
