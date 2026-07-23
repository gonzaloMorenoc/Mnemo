// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  getJiraConfig: vi.fn(),
  importKnowledge: vi.fn(),
}));

import { getJiraConfig, importKnowledge } from "@/lib/api/endpoints";
import { KnowledgeImportPanel } from "@/components/knowledge/KnowledgeImportPanel";

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KnowledgeImportPanel orgId="o1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("KnowledgeImportPanel", () => {
  it("sin integración configurada muestra el CTA a Integraciones", async () => {
    vi.mocked(getJiraConfig).mockResolvedValue({ configured: false });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /Integraciones/i })).toHaveAttribute(
        "href", "/app/integrations"));
    expect(screen.queryByRole("button", { name: /Generar propuestas/i })).toBeNull();
  });

  it("importa las refs del textarea y muestra el resumen", async () => {
    vi.mocked(getJiraConfig).mockResolvedValue({ configured: true });
    vi.mocked(importKnowledge).mockResolvedValue({
      created: [{ id: "p1" } as never],
      refreshed: [],
      skipped: ["PAY-2"],
      errors: [{ ref: "MAL", reason: "No parece una clave de Jira (formato PROJ-123)." }],
    });
    renderPanel();
    const textarea = await screen.findByLabelText(/Claves de Jira/i);
    fireEvent.change(textarea, { target: { value: "PAY-1\nPAY-2, MAL" } });
    fireEvent.click(screen.getByRole("button", { name: /Generar propuestas/i }));
    await waitFor(() =>
      expect(importKnowledge).toHaveBeenCalledWith("tok", "o1", ["PAY-1", "PAY-2", "MAL"]));
    expect(await screen.findByText(/1 nueva/i)).toBeInTheDocument();
    expect(screen.getByText(/1 omitida/i)).toBeInTheDocument();
    expect(screen.getByText(/No parece una clave de Jira/i)).toBeInTheDocument();
  });

  it("más de 10 refs deshabilita el botón y avisa", async () => {
    vi.mocked(getJiraConfig).mockResolvedValue({ configured: true });
    renderPanel();
    const textarea = await screen.findByLabelText(/Claves de Jira/i);
    const refs = Array.from({ length: 11 }, (_, i) => `PAY-${i}`).join("\n");
    fireEvent.change(textarea, { target: { value: refs } });
    expect(screen.getByText("11/10")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generar propuestas/i })).toBeDisabled();
  });
});
