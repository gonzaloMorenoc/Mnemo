// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { VerdictBadge } from "@/components/ui/verdict-badge";

afterEach(cleanup);

describe("VerdictBadge", () => {
  it("traduce los slugs de veredicto a etiquetas legibles", () => {
    const { rerender } = render(<VerdictBadge verdict="apto" />);
    expect(screen.getByText("Apto")).toBeInTheDocument();
    rerender(<VerdictBadge verdict="apto-con-reservas" />);
    expect(screen.getByText("Apto con reservas")).toBeInTheDocument();
    rerender(<VerdictBadge verdict="no-apto" />);
    expect(screen.getByText("No apto")).toBeInTheDocument();
  });

  it("muestra 'Inconcluso' para el 4º veredicto", () => {
    render(<VerdictBadge verdict="inconcluso" />);
    expect(screen.getByText("Inconcluso")).toBeInTheDocument();
  });

  it("sin veredicto muestra 'Sin veredicto aún'", () => {
    render(<VerdictBadge verdict={null} />);
    expect(screen.getByText("Sin veredicto aún")).toBeInTheDocument();
  });
});
