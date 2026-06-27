// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: () => ({
    activeOrgId: "o1",
    orgs: [{ id: "o1", name: "Test Org", join_code: "ABC", role: "owner", created_at: null }],
    setActiveOrgId: vi.fn(),
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api/endpoints", () => ({
  createKnowledge: vi.fn(),
  askKnowledge: vi.fn(),
  searchKnowledge: vi.fn(),
}));

import { createKnowledge, askKnowledge, searchKnowledge } from "@/lib/api/endpoints";
import { toast } from "sonner";
import KnowledgePage from "@/app/app/knowledge/page";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("KnowledgePage", () => {
  it("llama a createKnowledge al enviar el formulario de captura", async () => {
    (createKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue({
      id: "k1",
      kind: "leccion",
      title: "Evitar N+1",
      tags: [],
      confidence: "high",
      created_at: "2024-01-01T00:00:00Z",
    });

    renderWithClient(<KnowledgePage />);

    // Fill in the required title field
    const titleInput = screen.getByLabelText(/título/i);
    fireEvent.change(titleInput, { target: { value: "Evitar N+1" } });

    // Submit the form
    const submitButton = screen.getByRole("button", { name: /guardar conocimiento/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(createKnowledge).toHaveBeenCalledWith("tok", expect.objectContaining({
        org_id: "o1",
        title: "Evitar N+1",
      }));
    });

    expect(toast.success).toHaveBeenCalledWith("Conocimiento capturado.");
  });

  it("llama a askKnowledge y renderiza la respuesta con citas", async () => {
    (askKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue({
      answer: "Los pagos deben usar idempotency keys.",
      citations: ["Regla #12: idempotency en pagos", "Lección: doble cobro 2023"],
    });
    (searchKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderWithClient(<KnowledgePage />);

    const questionInput = screen.getByPlaceholderText(/qué quieres saber/i);
    fireEvent.change(questionInput, { target: { value: "¿Cómo gestionar pagos?" } });

    const askButton = screen.getByRole("button", { name: /preguntar/i });
    fireEvent.click(askButton);

    await waitFor(() => {
      expect(askKnowledge).toHaveBeenCalledWith("tok", {
        org_id: "o1",
        question: "¿Cómo gestionar pagos?",
      });
    });

    expect(await screen.findByText("Los pagos deben usar idempotency keys.")).toBeInTheDocument();
    expect(screen.getByText("· Regla #12: idempotency en pagos")).toBeInTheDocument();
    expect(screen.getByText("· Lección: doble cobro 2023")).toBeInTheDocument();
  });

  it("llama a toast.error si askKnowledge falla, sin romper la página", async () => {
    (askKnowledge as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Error de red"));

    renderWithClient(<KnowledgePage />);

    const questionInput = screen.getByPlaceholderText(/qué quieres saber/i);
    fireEvent.change(questionInput, { target: { value: "pregunta fallida" } });

    const askButton = screen.getByRole("button", { name: /preguntar/i });
    fireEvent.click(askButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Error de red");
    });

    // Page is still rendered — form is still visible
    expect(screen.getByRole("button", { name: /preguntar/i })).toBeInTheDocument();
  });
});
