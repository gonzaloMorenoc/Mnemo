// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  listProjects: vi.fn(), createProject: vi.fn(), updateProject: vi.fn(),
}));

import { createProject, listProjects, updateProject } from "@/lib/api/endpoints";
import { ProjectsPanel } from "@/components/org/ProjectsPanel";

const WEB = { id: "p1", key: "checkout-suite", name: "Checkout", is_example: false, archived: false,
  created_at: "", runs: 3, knowledge: 1 };

function renderPanel(role: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}><ProjectsPanel org={{ id: "o1", role }} /></QueryClientProvider>,
  );
}

afterEach(() => { vi.clearAllMocks(); cleanup(); });

describe("ProjectsPanel", () => {
  it("muestra nombre, clave y actividad; un viewer no puede tocar nada", async () => {
    vi.mocked(listProjects).mockResolvedValue([{ ...WEB, archived: true }]);
    renderPanel("viewer");
    expect(await screen.findByText("Checkout")).toBeInTheDocument();
    expect(screen.getByText("checkout-suite")).toBeInTheDocument();
    expect(screen.getByText(/3 runs · 1 elemento de conocimiento/)).toBeInTheDocument();
    expect(screen.getByText("archivado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Renombrar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear proyecto" })).not.toBeInTheDocument();
    expect(listProjects).toHaveBeenCalledWith("tok", "o1", true);
  });

  it("un admin renombra el nombre visible (la clave no se toca)", async () => {
    vi.mocked(listProjects).mockResolvedValue([WEB]);
    vi.mocked(updateProject).mockResolvedValue({ ...WEB, name: "Checkout web" });
    renderPanel("admin");
    fireEvent.click(await screen.findByRole("button", { name: "Renombrar" }));
    fireEvent.change(screen.getByLabelText("Nombre de checkout-suite"), { target: { value: "Checkout web" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledWith("tok", "p1", { name: "Checkout web" }));
  });

  it("un admin archiva y crea proyectos", async () => {
    vi.mocked(listProjects).mockResolvedValue([WEB]);
    vi.mocked(updateProject).mockResolvedValue({ ...WEB, archived: true });
    vi.mocked(createProject).mockResolvedValue({ ...WEB, id: "p2", key: "nuevo" });
    renderPanel("owner");
    fireEvent.click(await screen.findByRole("button", { name: "Archivar" }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledWith("tok", "p1", { archived: true }));
    fireEvent.change(screen.getByLabelText("Clave del nuevo proyecto"), { target: { value: " nuevo " } });
    fireEvent.click(screen.getByRole("button", { name: "Crear proyecto" }));
    await waitFor(() => expect(createProject).toHaveBeenCalledWith("tok", { org_id: "o1", key: "nuevo" }));
  });

  it("sin proyectos explica que se crean solos con la ingesta", async () => {
    vi.mocked(listProjects).mockResolvedValue([]);
    renderPanel("member");
    expect(await screen.findByText(/Se crean solos con la primera ingesta/)).toBeInTheDocument();
  });
});
