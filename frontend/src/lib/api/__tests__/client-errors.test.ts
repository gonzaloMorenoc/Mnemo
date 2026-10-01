import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest, ApiClientError } from "@/lib/api/client";

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), { status }),
  ));
}

async function errorOf(): Promise<ApiClientError> {
  try {
    await apiRequest("/api/v2/x", "GET");
  } catch (e) {
    return e as ApiClientError;
  }
  throw new Error("no lanzó");
}

afterEach(() => vi.unstubAllGlobals());

describe("apiRequest: mensajes de error que puede leer una persona", () => {
  it("un 4xx con detail de texto conserva el mensaje del backend", async () => {
    mockFetch(404, { detail: "proyecto no encontrado en esta organización" });
    const e = await errorOf();
    expect(e.message).toBe("proyecto no encontrado en esta organización");
    expect(e.status).toBe(404);
  });

  it("un 422 de validación (detail es una lista) no acaba en «[object Object]»", async () => {
    mockFetch(422, { detail: [{ loc: ["body", "x"], msg: "field required" }] });
    const e = await errorOf();
    expect(e.message).toBe("Hay datos que no son válidos. Revisa el formulario.");
    expect(e.details).toEqual({ detail: [{ loc: ["body", "x"], msg: "field required" }] });
  });

  it("un 5xx no enseña el texto interno del servidor", async () => {
    mockFetch(502, { detail: "Database error" });
    const e = await errorOf();
    expect(e.message).toBe("El servidor no ha podido completar la acción (error 502). Inténtalo de nuevo en unos segundos.");
    expect(e.status).toBe(502);
  });

  it("sin cuerpo, un mensaje en español con el código", async () => {
    mockFetch(418, "");
    expect((await errorOf()).message).toBe("No se pudo completar la acción (error 418).");
  });
});
