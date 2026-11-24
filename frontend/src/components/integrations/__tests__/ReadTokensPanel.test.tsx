// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  listIngestTokens: vi.fn(),
  createIngestToken: vi.fn(),
  revokeIngestToken: vi.fn(),
  listProjects: vi.fn(),
}));

import { ReadTokensPanel, clientSnippets } from "@/components/integrations/ReadTokensPanel";
import * as endpoints from "@/lib/api/endpoints";

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReadTokensPanel orgId="o1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("ReadTokensPanel", () => {
  it("pide solo los tokens de lectura y los lista con su alcance", async () => {
    vi.mocked(endpoints.listProjects).mockResolvedValue([]);
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([
      { id: "t1", name: "Claude · Ana", scope: "read", project: "checkout",
        expires_at: "2027-01-01T00:00:00Z", last_used_at: null, revoked_at: null },
      { id: "t2", name: "Viejo", scope: "read", project: null,
        expires_at: "2020-01-01T00:00:00Z", last_used_at: null, revoked_at: null },
    ]);
    renderPanel();
    expect(await screen.findByText("Claude · Ana")).toBeTruthy();
    expect(endpoints.listIngestTokens).toHaveBeenCalledWith("tok", "o1", "read");
    expect(screen.getByText(/proyecto checkout/)).toBeTruthy();
    expect(screen.getByText("Caducado")).toBeTruthy();
  });

  it("crea un token atado a un proyecto con caducidad y enseña la configuración", async () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([]);
    vi.mocked(endpoints.listProjects).mockResolvedValue([
      { id: "p1", key: "checkout", name: "Checkout", description: null, is_example: false,
        archived: false, created_at: "", runs: 1, last_run_at: null, knowledge: 0 },
    ]);
    vi.mocked(endpoints.createIngestToken).mockResolvedValue({
      id: "t9", name: "Claude", token: "mnemo_rt_secreto",
    });
    renderPanel();
    await screen.findByRole("option", { name: "Checkout" });
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Claude" } });
    fireEvent.change(screen.getByLabelText("Alcance"), { target: { value: "checkout" } });
    fireEvent.change(screen.getByLabelText("Caduca"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear token" }));
    await waitFor(() => expect(endpoints.createIngestToken).toHaveBeenCalledWith(
      "tok", "o1", "Claude", { scope: "read", project: "checkout", expires_in_days: 30 }));
    expect(await screen.findByText("mnemo_rt_secreto")).toBeTruthy();
    // La configuración nunca lleva el secreto.
    expect(screen.getByText(/claude mcp add/).textContent).not.toContain("mnemo_rt_secreto");
    fireEvent.click(screen.getByRole("tab", { name: "Cursor" }));
    expect(screen.getByText(/mcpServers/)).toBeTruthy();
  });

  it("sin caducidad no manda expires_in_days", async () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([]);
    vi.mocked(endpoints.listProjects).mockResolvedValue([]);
    vi.mocked(endpoints.createIngestToken).mockResolvedValue({ id: "t", name: "x", token: "y" });
    renderPanel();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText("Caduca"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear token" }));
    await waitFor(() => expect(endpoints.createIngestToken).toHaveBeenCalledWith(
      "tok", "o1", "x", { scope: "read" }));
  });
});

describe("clientSnippets", () => {
  it("cada cliente apunta a /mcp y lee el token de fuera", () => {
    for (const s of clientSnippets("https://api.example/mcp")) {
      expect(s.text).toContain("https://api.example/mcp");
      expect(s.text).not.toMatch(/mnemo_rt_[0-9a-f]/);
    }
  });
});
