// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// useSearchParams lee la query actual (reactivo): en el test lo derivamos de
// window.location, que cada render vuelve a leer → simula la navegación suave.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

import GuiaPage from "@/app/app/guia/page";
import { CHAPTERS } from "@/content/guia";

function setSearch(search: string) {
  window.history.replaceState({}, "", `/app/guia${search}`);
}

beforeEach(() => setSearch(""));
afterEach(cleanup);

describe("GuiaPage — deep-link por capítulo", () => {
  it("lista todos los capítulos en la barra lateral", () => {
    render(<GuiaPage />);
    for (const c of CHAPTERS) {
      expect(screen.getByRole("link", { name: c.title })).toBeInTheDocument();
    }
  });

  it("sin ?c= muestra el primer capítulo", () => {
    render(<GuiaPage />);
    expect(screen.getByRole("heading", { level: 1, name: CHAPTERS[0].title })).toBeInTheDocument();
  });

  it("con ?c=<slug> muestra ese capítulo", () => {
    const target = CHAPTERS[CHAPTERS.length - 1];
    setSearch(`?c=${target.slug}`);
    render(<GuiaPage />);
    expect(screen.getByRole("heading", { level: 1, name: target.title })).toBeInTheDocument();
  });

  it("con un slug desconocido cae al primer capítulo", () => {
    setSearch("?c=no-existe");
    render(<GuiaPage />);
    expect(screen.getByRole("heading", { level: 1, name: CHAPTERS[0].title })).toBeInTheDocument();
  });

  it("reacciona a un cambio de ?c= sin remontar (no hace falta refrescar)", () => {
    setSearch(`?c=${CHAPTERS[0].slug}`);
    const { rerender } = render(<GuiaPage />);
    expect(screen.getByRole("heading", { level: 1, name: CHAPTERS[0].title })).toBeInTheDocument();
    const target = CHAPTERS[CHAPTERS.length - 1];
    setSearch(`?c=${target.slug}`);
    rerender(<GuiaPage />);
    expect(screen.getByRole("heading", { level: 1, name: target.title })).toBeInTheDocument();
  });
});
