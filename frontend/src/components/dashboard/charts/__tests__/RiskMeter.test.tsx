// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RiskMeter } from "@/components/dashboard/charts/RiskMeter";

afterEach(cleanup);

describe("RiskMeter", () => {
  it("con score pinta el medidor y el valor", () => {
    render(<RiskMeter score={42} />);
    expect(screen.getByRole("img", { name: "Riesgo: 42 de 100" })).toBeInTheDocument();
    expect(screen.getByText("42/100")).toBeInTheDocument();
  });

  it("con score null muestra '—' (riesgo no aplica)", () => {
    render(<RiskMeter score={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/\/100/)).toBeNull();
  });
});
