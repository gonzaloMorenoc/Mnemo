// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RadialGauge } from "@/components/dashboard/charts/RadialGauge";

afterEach(cleanup);

describe("RadialGauge", () => {
  it("muestra el porcentaje redondeado y el aria-label", () => {
    render(<RadialGauge value={0.78} ariaLabel="Precisión del motor: 78%" />);
    expect(screen.getByRole("img", { name: "Precisión del motor: 78%" })).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });
});
