// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { HandoverStamp } from "@/components/verify/HandoverStamp";

const CANONICAL = {
  schema: "mnemo.traspaso.v1",
  project: "checkout-suite",
  created_at: "2026-08-13T10:00:00Z",
  key_id: "946152583e361f1e",
  continuity: {
    score: 42,
    dimensions: [
      { key: "oficio", label: "Oficio del proyecto", num: 2, den: 4, ratio: 0.5, weight: 0.25 },
      { key: "reglas_respaldadas", label: "Reglas con respaldo", num: 0, den: 0, ratio: null, weight: 0.15 },
    ],
  },
};

afterEach(cleanup);

describe("HandoverStamp", () => {
  it("pinta proyecto, índice y desglose", () => {
    render(<HandoverStamp canonical={CANONICAL} />);
    expect(screen.getByText(/acta de traspaso auténtica/i)).toBeInTheDocument();
    expect(screen.getByText("checkout-suite")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Oficio del proyecto")).toBeInTheDocument();
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("una dimensión sin denominador dice «sin datos», no 0", () => {
    render(<HandoverStamp canonical={CANONICAL} />);
    expect(screen.getByText("sin datos")).toBeInTheDocument();
  });

  it("score null se muestra como sin datos suficientes, no como 0", () => {
    render(
      <HandoverStamp
        canonical={{ ...CANONICAL, continuity: { score: null, dimensions: [] } }}
      />,
    );
    expect(screen.getByText(/sin datos suficientes/i)).toBeInTheDocument();
  });

  it("campo ausente → raya, nunca una etiqueta huérfana", () => {
    render(<HandoverStamp canonical={{ schema: "mnemo.traspaso.v1" }} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
