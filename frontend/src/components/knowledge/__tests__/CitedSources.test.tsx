// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CitedSources } from "@/components/knowledge/CitedSources";

afterEach(cleanup);

describe("CitedSources", () => {
  it("muestra el título y el tipo de cada fuente, no su id", () => {
    render(
      <CitedSources
        citations={["7330f4ee-dff6-4a1b-9c2d-000000000001"]}
        sources={[{ id: "7330f4ee-dff6-4a1b-9c2d-000000000001", type: "defect",
                    title: "Los timeouts correlan con runners fríos del sandbox del PSP" }]}
      />,
    );
    expect(screen.getByText("Los timeouts correlan con runners fríos del sandbox del PSP")).toBeInTheDocument();
    expect(screen.getByText("Defecto")).toBeInTheDocument();
    expect(screen.queryByText(/7330f4ee/)).not.toBeInTheDocument();
  });

  it("sin título del backend, cae a un id corto y no al UUID entero", () => {
    render(<CitedSources citations={["abcdef12-0000-0000-0000-000000000000"]} />);
    expect(screen.getByText("Fuente abcdef12")).toBeInTheDocument();
  });

  it("no pinta nada si no hay citas", () => {
    const { container } = render(<CitedSources citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
