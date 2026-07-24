// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { GuiaContent } from "@/components/guia/GuiaContent";
import type { Chapter } from "@/content/guia/types";

afterEach(cleanup);

const CH: Chapter = {
  slug: "demo",
  title: "Capítulo demo",
  summary: "Resumen del capítulo demo.",
  sections: [
    {
      heading: "Una sección",
      blocks: [
        { kind: "p", text: "Un párrafo con [Autopilot](/app/autopilot)." },
        { kind: "steps", items: ["Primer paso", "Segundo paso"] },
        { kind: "list", items: ["Una viñeta"] },
        { kind: "note", tone: "warn", text: "Un aviso importante." },
        { kind: "term", term: "triaje" },
      ],
    },
  ],
};

describe("GuiaContent", () => {
  it("pinta el título y el resumen del capítulo", () => {
    render(<GuiaContent chapter={CH} />);
    expect(screen.getByRole("heading", { name: "Capítulo demo" })).toBeInTheDocument();
    expect(screen.getByText("Resumen del capítulo demo.")).toBeInTheDocument();
  });

  it("pinta el heading de la sección", () => {
    render(<GuiaContent chapter={CH} />);
    expect(screen.getByRole("heading", { name: "Una sección" })).toBeInTheDocument();
  });

  it("pinta pasos en <ol> y viñetas en <ul>", () => {
    const { container } = render(<GuiaContent chapter={CH} />);
    expect(container.querySelector("ol")).toBeTruthy();
    expect(container.querySelector("ul")).toBeTruthy();
    expect(screen.getByText("Primer paso")).toBeInTheDocument();
    expect(screen.getByText("Una viñeta")).toBeInTheDocument();
  });

  it("pinta el enlace interno de un párrafo", () => {
    render(<GuiaContent chapter={CH} />);
    expect(screen.getByRole("link", { name: "Autopilot" })).toHaveAttribute("href", "/app/autopilot");
  });

  it("pinta el aviso y el bloque de término (con su definición del glosario)", () => {
    render(<GuiaContent chapter={CH} />);
    expect(screen.getByText("Un aviso importante.")).toBeInTheDocument();
    expect(
      screen.getByText(/Clasificación automática de un fallo/i),
    ).toBeInTheDocument();
  });
});
