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

function mockAuth() {
  (useAuth as ReturnType<typeof vi.fn>).mockReturnValue({
    user: { email: "a@b.c" },
    signOut: vi.fn(),
  });
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("Topbar — breadcrumb org / sección / página (sin título duplicado)", () => {
  it("muestra sección y página en el breadcrumb", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/integrations");
    mockAuth();
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    const crumb = screen.getByRole("navigation", { name: "Ruta de navegación" });
    expect(crumb).toHaveTextContent("Configuración");
    expect(crumb).toHaveTextContent("Integraciones");
  });

  it("resuelve subrutas dinámicas al item padre", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/defects/1b2c3d");
    mockAuth();
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(
      screen.getByRole("navigation", { name: "Ruta de navegación" }),
    ).toHaveTextContent("Defect DNA");
  });

  it("NO duplica el h1 de la página (el header ya no lleva heading)", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/integrations");
    mockAuth();
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(screen.queryByRole("heading")).toBeNull();
  });

  it("incluye el org-switcher y el botón 'Cerrar sesión'", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app");
    mockAuth();
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(screen.getByTestId("org-switcher")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cerrar sesión" })).toBeInTheDocument();
  });

  it("en una ruta desconocida no renderiza breadcrumb (solo el contexto de org)", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/ruta-desconocida");
    mockAuth();
    render(<Topbar onOpenMobileMenu={vi.fn()} />);
    expect(screen.queryByRole("navigation", { name: "Ruta de navegación" })).toBeNull();
  });
});
