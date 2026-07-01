// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: vi.fn(),
  useRouter: vi.fn(() => ({ replace: vi.fn() })),
}));

// Mock auth-provider
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: vi.fn(),
}));

// Mock OrgSwitcher
vi.mock("@/components/layout/org-switcher", () => ({
  OrgSwitcher: () => <div data-testid="org-switcher" />,
}));

import { usePathname } from "next/navigation";
import { useAuth } from "@/components/providers/auth-provider";
import { Topbar } from "@/components/layout/topbar";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("Topbar — título desde fuente única + localización", () => {
  it("muestra 'Integraciones' para /app/integrations (antes caía a Mnemo)", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/integrations");
    (useAuth as ReturnType<typeof vi.fn>).mockReturnValue({
      user: { email: "a@b.c" },
      signOut: vi.fn(),
    });
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Integraciones" })).toBeInTheDocument();
  });

  it("muestra 'Mnemo' cuando la ruta no está en el nav", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/unknown-route");
    (useAuth as ReturnType<typeof vi.fn>).mockReturnValue({
      user: { email: "a@b.c" },
      signOut: vi.fn(),
    });
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Mnemo" })).toBeInTheDocument();
  });

  it("muestra el botón 'Cerrar sesión'", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/integrations");
    (useAuth as ReturnType<typeof vi.fn>).mockReturnValue({
      user: { email: "a@b.c" },
      signOut: vi.fn(),
    });
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeInTheDocument();
  });

  it("no renderiza el subtítulo duplicado 'Mnemo' como párrafo", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/integrations");
    (useAuth as ReturnType<typeof vi.fn>).mockReturnValue({
      user: { email: "a@b.c" },
      signOut: vi.fn(),
    });
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    // Only the h1 heading should exist — no secondary <p>Mnemo</p> subtitle
    const heading = screen.getByRole("heading", { name: "Integraciones" });
    expect(heading).toBeInTheDocument();
    // There should be no <p> element containing just "Mnemo" as subtitle
    const allParagraphs = document.querySelectorAll("p");
    const mnemoSubtitle = Array.from(allParagraphs).find((p) => p.textContent === "Mnemo");
    expect(mnemoSubtitle).toBeUndefined();
  });
});
