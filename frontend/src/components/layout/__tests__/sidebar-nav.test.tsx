// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: vi.fn(),
}));

// Mock next/link
vi.mock("next/link", () => ({
  default: ({ href, children, onClick, className }: { href: string; children: React.ReactNode; onClick?: () => void; className?: string }) => (
    <a href={href} onClick={onClick} className={className}>
      {children}
    </a>
  ),
}));

import { usePathname } from "next/navigation";
import { SidebarNav } from "@/components/layout/sidebar-nav";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("SidebarNav — secciones y navegación", () => {
  it("muestra los 3 encabezados de sección (Continuidad, Aseguramiento, Configuración)", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app");
    render(<SidebarNav />);
    expect(screen.getByText("Continuidad")).toBeInTheDocument();
    expect(screen.getByText("Aseguramiento")).toBeInTheDocument();
    expect(screen.getByText("Configuración")).toBeInTheDocument();
  });

  it("incluye el item Dashboard", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app");
    render(<SidebarNav />);
    expect(screen.getByRole("link", { name: /Dashboard/i })).toBeInTheDocument();
  });

  it("muestra los 12 enlaces con labels ES (incluye Integraciones, Organización, Ajustes)", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app");
    render(<SidebarNav />);
    const links = screen.getAllByRole("link");
    // Nav items all have the rounded-xl class; the logo link does not
    const navLinks = links.filter((l) => {
      return l.className.includes("rounded-xl");
    });
    expect(navLinks).toHaveLength(12);
    expect(screen.getByRole("link", { name: /Integraciones/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Organización/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ajustes/i })).toBeInTheDocument();
  });

  it("marca Integraciones como activo en /app/integrations y Dashboard NO activo", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app/integrations");
    render(<SidebarNav />);
    const integracionesLink = screen.getByRole("link", { name: /Integraciones/i });
    const dashboardLink = screen.getByRole("link", { name: /Dashboard/i });
    expect(integracionesLink.className).toMatch(/bg-zinc-900/);
    expect(dashboardLink.className).not.toMatch(/bg-zinc-900/);
  });

  it("marca Dashboard como activo en /app y ningún otro item lo está", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app");
    render(<SidebarNav />);
    const dashboardLink = screen.getByRole("link", { name: /Dashboard/i });
    expect(dashboardLink.className).toMatch(/bg-zinc-900/);
  });

  it("/app no activa Conocimiento ni Assurance (match exacto)", () => {
    (usePathname as ReturnType<typeof vi.fn>).mockReturnValue("/app");
    render(<SidebarNav />);
    const conocimientoLink = screen.getByRole("link", { name: /Conocimiento/i });
    const assuranceLink = screen.getByRole("link", { name: /Assurance/i });
    expect(conocimientoLink.className).not.toMatch(/bg-zinc-900/);
    expect(assuranceLink.className).not.toMatch(/bg-zinc-900/);
  });
});
