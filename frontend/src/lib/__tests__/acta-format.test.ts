import { describe, expect, it } from "vitest";

import { fechaActa, refCommit } from "@/lib/acta-format";

describe("formato de los datos del acta en el sello", () => {
  it("la fecha se lee como fecha, en UTC (la zona en la que se firma), sin microsegundos", () => {
    expect(fechaActa("2026-07-15T16:46:04.982507+00:00")).toBe("15 de julio de 2026, 16:46 UTC");
  });

  it("una fecha ausente o no válida no se inventa", () => {
    expect(fechaActa("")).toBe("");
    expect(fechaActa("no es una fecha")).toBe("no es una fecha");
  });

  it("un SHA de git se acorta; cualquier otra referencia se muestra entera", () => {
    expect(refCommit("a1b2c3d4e5f60718293a4b5c6d7e8f9012345678")).toBe("a1b2c3d4e5f6");
    expect(refCommit("demo-real-001")).toBe("demo-real-001");
  });
});
