import { describe, expect, it } from "vitest";

import { crumbForPath } from "@/components/layout/nav";

describe("crumbForPath — breadcrumb con prefix-match", () => {
  it("resuelve una ruta exacta con su sección", () => {
    expect(crumbForPath("/app/knowledge")).toEqual({
      section: "Memoria",
      label: "Conocimiento",
    });
  });

  it("resuelve subrutas dinámicas (detalle de familia) al item padre", () => {
    expect(crumbForPath("/app/defects/1b2c3d")).toEqual({
      section: "Aseguramiento",
      label: "Defect DNA",
    });
  });

  it("el Dashboard solo casa con /app exacto", () => {
    expect(crumbForPath("/app")).toEqual({ section: null, label: "Dashboard" });
    expect(crumbForPath("/app/ruta-desconocida")).toBeNull();
  });

  it("rutas fuera del nav devuelven null", () => {
    expect(crumbForPath("/otra-cosa")).toBeNull();
  });
});
