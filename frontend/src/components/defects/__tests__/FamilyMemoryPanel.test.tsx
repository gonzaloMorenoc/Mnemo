// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  listKnowledge: vi.fn(),
  generateKnowledgeProposals: vi.fn(),
}));

import { FamilyMemoryPanel } from "@/components/defects/FamilyMemoryPanel";
import * as endpoints from "@/lib/api/endpoints";
import type { KnowledgeItem } from "@/lib/api/types";

const LESSON: KnowledgeItem = {
  id: "k1", kind: "leccion", title: "El PSP tarda en sandbox",
  approach: "Etiquetar los 429 como infra", tags: [], confidence: "inferido",
  created_at: "2026-07-22T00:00:00", status: "activo", source: "auto_triage",
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FamilyMemoryPanel token="tok" orgId="o1" familyId="f1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("FamilyMemoryPanel (memoria en el flujo)", () => {
  it("muestra la lección vinculada a la familia (solo activas)", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([LESSON]);
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText("El PSP tarda en sandbox")).toBeInTheDocument());
    expect(screen.getByText("Lección")).toBeInTheDocument();
    expect(endpoints.listKnowledge).toHaveBeenCalledWith("tok", "o1", {
      defect_family_id: "f1",
      status: "activo",
    });
  });

  it("sin lección: ofrece 'Proponer lección (IA)' acotado a la familia", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([]);
    vi.mocked(endpoints.generateKnowledgeProposals).mockResolvedValue(
      { created: 1, failed: 0, remaining: 0 });
    renderPanel();
    await screen.findByText("Esta familia aún no tiene lección documentada.");
    fireEvent.click(screen.getByRole("button", { name: /Proponer lección/i }));
    await waitFor(() =>
      expect(endpoints.generateKnowledgeProposals).toHaveBeenCalledWith("tok", "o1", {
        cap: 1,
        familyIds: ["f1"],
      }));
  });
});
