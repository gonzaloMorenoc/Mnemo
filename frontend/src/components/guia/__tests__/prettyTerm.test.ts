import { describe, expect, it } from "vitest";

import { prettyTerm } from "@/components/guia/TermChip";

describe("prettyTerm", () => {
  it("usa el nombre propio del mapa cuando existe (acento/gramática)", () => {
    expect(prettyTerm("self_heal")).toBe("autoreparación");
    expect(prettyTerm("calibracion")).toBe("calibración");
    expect(prettyTerm("precision_motor")).toBe("precisión del motor");
    expect(prettyTerm("familia_defectos")).toBe("familia de defectos");
  });

  it("cae a underscore→espacio cuando no hay entrada en el mapa", () => {
    expect(prettyTerm("triaje")).toBe("triaje");
    expect(prettyTerm("risk_score")).toBe("risk score");
  });
});
