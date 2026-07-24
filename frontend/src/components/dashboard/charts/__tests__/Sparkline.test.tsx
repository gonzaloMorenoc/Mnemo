// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Sparkline } from "@/components/dashboard/charts/Sparkline";

afterEach(cleanup);

describe("Sparkline", () => {
  it("pinta una polyline con un punto por valor y expone aria-label", () => {
    const { container } = render(<Sparkline values={[50, 40, 42]} ariaLabel="Riesgo de 50 a 42" />);
    expect(screen.getByRole("img", { name: "Riesgo de 50 a 42" })).toBeInTheDocument();
    const pts = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(pts.trim().split(/\s+/)).toHaveLength(3);
  });

  it("no renderiza nada con menos de 2 valores (el consumidor pone el mensaje)", () => {
    const { container } = render(<Sparkline values={[42]} ariaLabel="x" />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
