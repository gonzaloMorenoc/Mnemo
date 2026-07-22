// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  listKnowledge: vi.fn(),
  updateKnowledge: vi.fn(),
  deleteKnowledge: vi.fn(),
}));

import { KnowledgeBrowser } from "@/components/knowledge/KnowledgeBrowser";
import * as endpoints from "@/lib/api/endpoints";
import type { KnowledgeItem } from "@/lib/api/types";

const ITEM: KnowledgeItem = {
  id: "k1", kind: "leccion", title: "Timeout del PSP", challenge: "El widget tarda",
  approach: "Etiquetar como infra", outcome: undefined, domain: "checkout",
  tags: ["web"], confidence: "confirmado", created_at: "2026-07-22T00:00:00",
  status: "activo", source: "manual",
};

function renderBrowser() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KnowledgeBrowser orgId="o1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("KnowledgeBrowser (hojeo + curación)", () => {
  it("lista los items con su tipo y dominio", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([ITEM]);
    renderBrowser();
    await waitFor(() => expect(screen.getByText("Timeout del PSP")).toBeInTheDocument());
    expect(screen.getByText("Lección")).toBeInTheDocument();
    expect(endpoints.listKnowledge).toHaveBeenCalledWith("tok", "o1", {});
  });

  it("'Marcar obsoleto' hace PATCH con status=obsoleto", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([ITEM]);
    vi.mocked(endpoints.updateKnowledge).mockResolvedValue({ ...ITEM, status: "obsoleto" });
    renderBrowser();
    await screen.findByText("Timeout del PSP");
    fireEvent.click(screen.getByRole("button", { name: /Marcar obsoleto/i }));
    await waitFor(() =>
      expect(endpoints.updateKnowledge).toHaveBeenCalledWith("tok", "k1", {
        org_id: "o1",
        status: "obsoleto",
      }));
  });

  it("Editar → Guardar envía los campos editados", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([ITEM]);
    vi.mocked(endpoints.updateKnowledge).mockResolvedValue({ ...ITEM, title: "Editado" });
    renderBrowser();
    await screen.findByText("Timeout del PSP");
    fireEvent.click(screen.getByRole("button", { name: /^Editar$/i }));
    const title = screen.getByDisplayValue("Timeout del PSP");
    fireEvent.change(title, { target: { value: "Editado" } });
    fireEvent.click(screen.getByRole("button", { name: /^Guardar$/i }));
    await waitFor(() => expect(endpoints.updateKnowledge).toHaveBeenCalled());
    const [, itemId, body] = vi.mocked(endpoints.updateKnowledge).mock.calls[0];
    expect(itemId).toBe("k1");
    expect(body.title).toBe("Editado");
    expect(body.tags).toEqual(["web"]);
  });

  it("Borrar pide confirmación y llama a deleteKnowledge", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([ITEM]);
    vi.mocked(endpoints.deleteKnowledge).mockResolvedValue({ deleted: true });
    renderBrowser();
    await screen.findByText("Timeout del PSP");
    fireEvent.click(screen.getByRole("button", { name: /^Borrar$/i }));
    // confirma en el diálogo
    fireEvent.click(await screen.findByRole("button", { name: /^Borrar$/i, hidden: false }));
    await waitFor(() =>
      expect(endpoints.deleteKnowledge).toHaveBeenCalledWith("tok", "k1", "o1"));
  });

  it("un item obsoleto muestra la insignia y ofrece Reactivar", async () => {
    vi.mocked(endpoints.listKnowledge).mockResolvedValue([{ ...ITEM, status: "obsoleto" }]);
    renderBrowser();
    await screen.findByText("Timeout del PSP");
    expect(screen.getByText("Obsoleto")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reactivar/i })).toBeInTheDocument();
  });
});
