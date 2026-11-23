import { afterEach, describe, expect, it, vi } from "vitest";

import { HEALTH_PATH, pingBackend, resetWarmupForTests, warmBackend } from "@/lib/warmup";

function response(status: number) {
  return new Response("{}", { status });
}

afterEach(() => {
  resetWarmupForTests();
  vi.unstubAllGlobals();
});

describe("calentamiento del backend", () => {
  it("un 200 del health es «listo»", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200));
    vi.stubGlobal("fetch", fetchMock);
    await expect(pingBackend()).resolves.toBe("ready");
    expect(fetchMock).toHaveBeenCalledWith(HEALTH_PATH, expect.objectContaining({ cache: "no-store" }));
  });

  it("un 504 o un fallo de red se reintenta y acaba en «listo» si despierta", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(504))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(response(200));
    vi.stubGlobal("fetch", fetchMock);
    await expect(pingBackend({ retryDelayMs: 0 })).resolves.toBe("ready");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("si no despierta tras los intentos, «inalcanzable» (sin lanzar)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(502)));
    await expect(pingBackend({ retryDelayMs: 0, attempts: 2 })).resolves.toBe("unreachable");
  });

  it("warmBackend solo hace un ping por carga de página", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(200));
    vi.stubGlobal("fetch", fetchMock);
    await Promise.all([warmBackend(), warmBackend()]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
