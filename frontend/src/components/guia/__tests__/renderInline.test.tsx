// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { renderInline } from "@/components/guia/renderInline";

afterEach(cleanup);

function renderNodes(text: string) {
  return render(<p>{renderInline(text)}</p>);
}

describe("renderInline — parser inline-lite", () => {
  it("pinta **negrita** como <strong>", () => {
    renderNodes("esto es **importante** aquí");
    const strong = screen.getByText("importante");
    expect(strong.tagName).toBe("STRONG");
  });

  it("pinta `código` como <code>", () => {
    renderNodes("usa `junit.xml` como reporte");
    const code = screen.getByText("junit.xml");
    expect(code.tagName).toBe("CODE");
  });

  it("pinta [texto](/app/ruta) como enlace interno", () => {
    renderNodes("ve a [Autopilot](/app/autopilot) para analizar");
    const link = screen.getByRole("link", { name: "Autopilot" });
    expect(link).toHaveAttribute("href", "/app/autopilot");
  });

  it("pinta [[termino]] con su chip de término y tooltip del glosario", () => {
    renderNodes("el [[triaje]] clasifica cada fallo");
    expect(screen.getByText("triaje")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Qué es: triaje/i })).toBeInTheDocument();
  });

  it("renderiza '<' como texto literal, no como HTML", () => {
    renderNodes("si a < b entonces falla");
    expect(screen.getByText(/si a < b entonces falla/)).toBeInTheDocument();
  });

  it("combina varios tokens en una frase", () => {
    renderNodes("sube `junit.xml` y mira el [[triaje]] en **Autopilot**");
    expect(screen.getByText("junit.xml").tagName).toBe("CODE");
    expect(screen.getByText("triaje")).toBeInTheDocument();
    expect(screen.getByText("Autopilot").tagName).toBe("STRONG");
  });
});
