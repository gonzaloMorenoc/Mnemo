import { describe, expect, it } from "vitest";

import { continuityBand, deltaDesdeActa } from "@/lib/continuity-band";

describe("banda de riesgo del índice de continuidad", () => {
  it("por debajo de 50, riesgo alto (rojo)", () => {
    const b = continuityBand(25);
    expect(b.key).toBe("alto");
    expect(b.label).toBe("Riesgo alto");
    expect(b.bar).toContain("red");
  });

  it("de 50 a 79, riesgo medio (ámbar); desde 80, cubierto (verde)", () => {
    expect(continuityBand(50).key).toBe("medio");
    expect(continuityBand(79).key).toBe("medio");
    expect(continuityBand(80).key).toBe("cubierto");
    expect(continuityBand(95).bar).toContain("emerald");
  });

  it("sin datos no es un riesgo inventado", () => {
    const b = continuityBand(null);
    expect(b.key).toBe("sin-datos");
    expect(b.label).toBe("Sin datos");
  });

  it("los titulares hablan de lo documentado, no prometen porcentajes", () => {
    for (const s of [10, 60, 90]) {
      expect(continuityBand(s).headline).not.toMatch(/%/);
    }
  });
});

describe("diferencia frente a la última acta de traspaso", () => {
  it("dice cuánto ha subido o bajado el índice desde la última acta", () => {
    expect(deltaDesdeActa(95, 25)).toBe("+70 desde la última acta");
    expect(deltaDesdeActa(40, 55)).toBe("−15 desde la última acta");
    expect(deltaDesdeActa(60, 60)).toBe("igual que en la última acta");
  });

  it("sin acta o sin índice, no hay diferencia que contar", () => {
    expect(deltaDesdeActa(60, null)).toBeNull();
    expect(deltaDesdeActa(null, 60)).toBeNull();
  });
});
