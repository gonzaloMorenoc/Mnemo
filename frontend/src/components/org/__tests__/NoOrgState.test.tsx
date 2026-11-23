// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: vi.fn(),
}));
vi.mock("@/lib/api/endpoints", () => ({
  createOrganization: vi.fn(),
  joinOrganization: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ usePathname: () => "/app/continuity" }));

import { useActiveOrg } from "@/components/providers/org-provider";
import { createOrganization, joinOrganization } from "@/lib/api/endpoints";
import { NoOrgState } from "@/components/org/NoOrgState";
import { OrgGate } from "@/components/org/OrgGate";

const ORG = { id: "org-1", name: "Mi consultora", join_code: "AB12CD", role: "owner", created_at: null };

function orgCtx(overrides: Partial<ReturnType<typeof useActiveOrg>> = {}) {
  return {
    orgs: [],
    activeOrgId: "",
    isLoading: false,
    isError: false,
    hasNoOrgs: true,
    refetchOrgs: vi.fn(),
    setActiveOrgId: vi.fn(),
    ...overrides,
  } as ReturnType<typeof useActiveOrg>;
}

function renderUi(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("NoOrgState", () => {
  it("ofrece crear organización y unirse con código, con campos etiquetados", () => {
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx());
    renderUi(<NoOrgState />);
    expect(screen.getByLabelText(/Nombre de tu organización/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Código de invitación/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crear organización" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unirme con un código" })).toBeInTheDocument();
  });

  it("crear organización la activa", async () => {
    const setActiveOrgId = vi.fn();
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx({ setActiveOrgId }));
    vi.mocked(createOrganization).mockResolvedValue(ORG);
    renderUi(<NoOrgState />);
    fireEvent.change(screen.getByLabelText(/Nombre de tu organización/), { target: { value: "Mi consultora" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear organización" }));
    await waitFor(() => expect(setActiveOrgId).toHaveBeenCalledWith("org-1"));
    expect(createOrganization).toHaveBeenCalledWith("tok", { name: "Mi consultora" });
  });

  it("unirse con código la activa", async () => {
    const setActiveOrgId = vi.fn();
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx({ setActiveOrgId }));
    vi.mocked(joinOrganization).mockResolvedValue(ORG);
    renderUi(<NoOrgState />);
    fireEvent.change(screen.getByLabelText(/Código de invitación/), { target: { value: " AB12CD " } });
    fireEvent.click(screen.getByRole("button", { name: "Unirme con un código" }));
    await waitFor(() => expect(setActiveOrgId).toHaveBeenCalledWith("org-1"));
    expect(joinOrganization).toHaveBeenCalledWith("tok", { join_code: "AB12CD" });
  });

  it("valida antes de llamar al backend", async () => {
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx());
    renderUi(<NoOrgState />);
    fireEvent.click(screen.getByRole("button", { name: "Crear organización" }));
    expect(await screen.findByText(/al menos 2 caracteres/)).toBeInTheDocument();
    expect(createOrganization).not.toHaveBeenCalled();
  });

  it("un error del backend se enseña junto al formulario", async () => {
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx());
    vi.mocked(joinOrganization).mockRejectedValue(new Error("Código no válido."));
    renderUi(<NoOrgState />);
    fireEvent.change(screen.getByLabelText(/Código de invitación/), { target: { value: "ZZZZZZ" } });
    fireEvent.click(screen.getByRole("button", { name: "Unirme con un código" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Código no válido.");
  });
});

describe("OrgGate", () => {
  it("sin organizaciones enseña el estado compartido en vez de la página", () => {
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx());
    renderUi(<OrgGate><p>contenido</p></OrgGate>);
    expect(screen.queryByText("contenido")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crear organización" })).toBeInTheDocument();
  });

  it("con organización deja pasar la página", () => {
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx({ hasNoOrgs: false, activeOrgId: "o1", orgs: [ORG] }));
    renderUi(<OrgGate><p>contenido</p></OrgGate>);
    expect(screen.getByText("contenido")).toBeInTheDocument();
  });

  it("si falla la carga sin org conocida, ofrece reintentar (no «sin organización»)", () => {
    const refetchOrgs = vi.fn();
    vi.mocked(useActiveOrg).mockReturnValue(orgCtx({ hasNoOrgs: false, isError: true, refetchOrgs }));
    renderUi(<OrgGate><p>contenido</p></OrgGate>);
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(refetchOrgs).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Crear organización" })).not.toBeInTheDocument();
  });
});
