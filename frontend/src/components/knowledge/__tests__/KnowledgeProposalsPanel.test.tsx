// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  listKnowledgeProposals: vi.fn(),
  generateKnowledgeProposals: vi.fn(),
  approveKnowledgeProposal: vi.fn(),
  rejectKnowledgeProposal: vi.fn(),
}));

import { KnowledgeProposalsPanel } from "@/components/knowledge/KnowledgeProposalsPanel";
import * as endpoints from "@/lib/api/endpoints";
import type { KnowledgeProposal } from "@/lib/api/types";

const PROPOSAL: KnowledgeProposal = {
  id: "p1", org_id: "o1", defect_family_id: "f1", run_id: null, kind: "leccion",
  title: "Timeout en checkout", challenge: "causa", approach: "fix", domain: null,
  outcome: null, tags: ["web"], status: "pending", created_at: null,
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KnowledgeProposalsPanel orgId="o1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("KnowledgeProposalsPanel", () => {
  it("lista las propuestas pendientes (título editable)", async () => {
    vi.mocked(endpoints.listKnowledgeProposals).mockResolvedValue([PROPOSAL]);
    renderPanel();
    await waitFor(() =>
      expect(screen.getByDisplayValue("Timeout en checkout")).toBeInTheDocument());
    expect(endpoints.listKnowledgeProposals).toHaveBeenCalledWith("tok", "o1");
  });

  it("'Generar propuestas' llama a generate", async () => {
    vi.mocked(endpoints.listKnowledgeProposals).mockResolvedValue([]);
    vi.mocked(endpoints.generateKnowledgeProposals).mockResolvedValue(
      { created: 2, failed: 0, remaining: 1 });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText("No hay propuestas pendientes.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Generar propuestas/i }));
    await waitFor(() =>
      expect(endpoints.generateKnowledgeProposals).toHaveBeenCalledWith("tok", "o1"));
  });

  it("Aprobar envía los campos EDITADOS (no re-serializa el original)", async () => {
    vi.mocked(endpoints.listKnowledgeProposals).mockResolvedValue([PROPOSAL]);
    vi.mocked(endpoints.approveKnowledgeProposal).mockResolvedValue(
      { id: "k1", kind: "leccion", title: "T", domain: null, tags: [], confidence: "inferido", created_at: "x" });
    renderPanel();
    const titleInput = await screen.findByDisplayValue("Timeout en checkout");
    fireEvent.change(titleInput, { target: { value: "Timeout editado" } });
    fireEvent.click(screen.getByRole("button", { name: /^Aprobar$/i }));
    await waitFor(() => expect(endpoints.approveKnowledgeProposal).toHaveBeenCalled());
    const call = vi.mocked(endpoints.approveKnowledgeProposal).mock.calls[0];
    expect(call[0]).toBe("tok");
    expect(call[1]).toBe("p1");
    expect(call[2].title).toBe("Timeout editado");
    expect(call[2].kind).toBe("leccion");
  });

  it("Descartar llama a reject", async () => {
    vi.mocked(endpoints.listKnowledgeProposals).mockResolvedValue([PROPOSAL]);
    vi.mocked(endpoints.rejectKnowledgeProposal).mockResolvedValue({ rejected: true });
    renderPanel();
    await screen.findByDisplayValue("Timeout en checkout");
    fireEvent.click(screen.getByRole("button", { name: /Descartar/i }));
    await waitFor(() =>
      expect(endpoints.rejectKnowledgeProposal).toHaveBeenCalledWith("tok", "p1"));
  });
});
