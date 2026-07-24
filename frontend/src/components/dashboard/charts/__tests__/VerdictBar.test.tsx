// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { VerdictBar } from "@/components/dashboard/charts/VerdictBar";

afterEach(cleanup);

describe("VerdictBar", () => {
  it("pinta una fila por veredicto presente con su conteo y aria-label", () => {
    render(<VerdictBar counts={{ apto: 12, "no-apto": 2 }} />);
    const el = screen.getByRole("img");
    expect(el.getAttribute("aria-label")).toContain("12 Apto");
    expect(el.getAttribute("aria-label")).toContain("2 No apto");
    expect(screen.getByText("Apto")).toBeInTheDocument();
    expect(screen.getByText("No apto")).toBeInTheDocument();
  });

  it("sin veredictos muestra un mensaje", () => {
    render(<VerdictBar counts={{}} />);
    expect(screen.getByText("Sin veredictos aún.")).toBeInTheDocument();
  });
});
