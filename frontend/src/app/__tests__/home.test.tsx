// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) => (
    <a href={href} className={className}>{children}</a>
  ),
}));

import HomePage from "@/app/page";

afterEach(cleanup);

describe("HomePage (landing)", () => {
  it("muestra la tesis del producto en el titular", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: /Cada release, con su acta firmada/i, level: 1 }),
    ).toBeInTheDocument();
  });

  it("ofrece las dos CTA: Entrar y Verificar un acta (sin cuenta)", () => {
    render(<HomePage />);
    expect(screen.getByRole("link", { name: /Entrar/i })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: /Verificar un acta/i })).toHaveAttribute(
      "href",
      "/verify",
    );
  });

  it("presenta los tres pilares", () => {
    render(<HomePage />);
    expect(screen.getByText("Acta firmada verificable")).toBeInTheDocument();
    expect(screen.getByText("Memoria que aprende")).toBeInTheDocument();
    expect(screen.getByText("Se enchufa a tu CI")).toBeInTheDocument();
  });

  it("no vende ya 'Ollama / 0 € de API / on-premise' (copy obsoleto retirado)", () => {
    render(<HomePage />);
    expect(screen.queryByText(/Ollama/i)).toBeNull();
    expect(screen.queryByText(/on-premise/i)).toBeNull();
  });
});
