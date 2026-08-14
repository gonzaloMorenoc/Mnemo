import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "../handover/route";
import { proxyToBackend } from "@/lib/server/proxy";

vi.mock("@/lib/server/proxy", () => ({
  proxyToBackend: vi.fn(),
}));

/**
 * El backend valida el body con Pydantic (org_id + project): si el route
 * handler no lo reenvía, FastAPI responde 422 y "Emitir acta de traspaso"
 * muere en silencio. Regresión real detectada en producción.
 */
describe("POST /api/v2/continuity/handover", () => {
  beforeEach(() => {
    vi.mocked(proxyToBackend).mockClear();
  });

  it("reenvía el body JSON del cliente al backend", async () => {
    const body = JSON.stringify({ org_id: "org-1", project: "checkout-suite" });
    const request = new NextRequest("http://localhost/api/v2/continuity/handover", {
      method: "POST",
      body,
    });

    await POST(request);

    expect(proxyToBackend).toHaveBeenCalledWith(request, "/v2/continuity/handover", {
      method: "POST",
      body,
      contentType: "application/json",
    });
  });
});
