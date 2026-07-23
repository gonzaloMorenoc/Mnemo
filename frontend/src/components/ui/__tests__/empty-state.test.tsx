// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Dna } from "lucide-react";

import { EmptyState } from "@/components/ui/empty-state";

afterEach(cleanup);

describe("EmptyState", () => {
  it("muestra título, descripción y el CTA como enlace", () => {
    render(
      <EmptyState
        icon={Dna}
        title="Aún no hay familias"
        description="Analiza un run y aparecerán aquí."
        actionHref="/app/autopilot"
        actionLabel="Analizar un run"
      />,
    );
    expect(screen.getByText("Aún no hay familias")).toBeInTheDocument();
    expect(screen.getByText("Analiza un run y aparecerán aquí.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analizar un run" })).toHaveAttribute(
      "href",
      "/app/autopilot",
    );
  });

  it("sin actionHref no renderiza ningún enlace", () => {
    render(<EmptyState icon={Dna} title="Vacío" description="Nada que ver." />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
