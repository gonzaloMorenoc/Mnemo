// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
const org = { activeOrgId: "o1" };
vi.mock("@/components/providers/org-provider", () => ({ useActiveOrg: () => org }));
vi.mock("@/lib/api/endpoints", () => ({ listProjects: vi.fn() }));

import { listProjects } from "@/lib/api/endpoints";
import {
  ProjectProvider, projectParam, useActiveProject,
} from "@/components/providers/project-provider";
import { ProjectSwitcher } from "@/components/layout/project-switcher";

const P = (key: string) => ({ id: key, key, name: key.toUpperCase(), is_example: false,
  archived: false, created_at: "", runs: 0, knowledge: 0 });

function Probe() {
  const { activeProject, setActiveProject } = useActiveProject();
  return (
    <>
      <span data-testid="active">{activeProject || "todos"}</span>
      <button type="button" onClick={() => setActiveProject("web")}>elegir web</button>
      <button type="button" onClick={() => setActiveProject("")}>elegir todos</button>
    </>
  );
}

function renderTree() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProjectProvider><Probe /><ProjectSwitcher /></ProjectProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => { window.localStorage.clear(); org.activeOrgId = "o1"; });
afterEach(() => { vi.clearAllMocks(); cleanup(); });

describe("ProjectProvider", () => {
  it("pide solo los proyectos activos y empieza en «todos»", async () => {
    vi.mocked(listProjects).mockResolvedValue([P("web"), P("app")]);
    renderTree();
    expect(await screen.findByRole("combobox", { name: "Proyecto" })).toBeInTheDocument();
    expect(listProjects).toHaveBeenCalledWith("tok", "o1", false);
    expect(screen.getByTestId("active")).toHaveTextContent("todos");
  });

  it("recuerda el proyecto elegido por organización", async () => {
    vi.mocked(listProjects).mockResolvedValue([P("web")]);
    renderTree();
    await screen.findByRole("combobox", { name: "Proyecto" });
    fireEvent.click(screen.getByRole("button", { name: "elegir web" }));
    expect(screen.getByTestId("active")).toHaveTextContent("web");
    expect(window.localStorage.getItem("mnemo.activeProject.o1")).toBe("web");
    fireEvent.click(screen.getByRole("button", { name: "elegir todos" }));
    expect(window.localStorage.getItem("mnemo.activeProject.o1")).toBeNull();
  });

  it("un proyecto guardado que ya no existe (archivado) vuelve a «todos»", async () => {
    window.localStorage.setItem("mnemo.activeProject.o1", "viejo");
    vi.mocked(listProjects).mockResolvedValue([P("web")]);
    renderTree();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(screen.getByTestId("active")).toHaveTextContent("todos");
  });

  it("sin proyectos no hay selector", async () => {
    vi.mocked(listProjects).mockResolvedValue([]);
    renderTree();
    await waitFor(() => expect(listProjects).toHaveBeenCalled());
    expect(screen.queryByRole("combobox", { name: "Proyecto" })).not.toBeInTheDocument();
  });

  it("projectParam omite la clave cuando el filtro es «todos»", () => {
    expect(projectParam("")).toEqual({});
    expect(projectParam("web")).toEqual({ project: "web" });
  });
});
