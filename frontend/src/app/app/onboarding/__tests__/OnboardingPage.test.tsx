// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));

const mockActiveOrg: { value: string | null; isLoading: boolean } = { value: "o1", isLoading: false };

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: () => ({
    activeOrgId: mockActiveOrg.value,
    isLoading: mockActiveOrg.isLoading,
    orgs: mockActiveOrg.value
      ? [{ id: "o1", name: "Test Org", join_code: "ABC", role: "owner", created_at: null }]
      : [],
    setActiveOrgId: vi.fn(),
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api/endpoints", () => ({
  domainSummary: vi.fn(),
  learningPath: vi.fn(),
  askKnowledge: vi.fn(),
}));

import { domainSummary, learningPath, askKnowledge } from "@/lib/api/endpoints";
import { toast } from "sonner";
import OnboardingPage from "@/app/app/onboarding/page";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
  mockActiveOrg.value = "o1";
  mockActiveOrg.isLoading = false;
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const MOCK_SUMMARY = {
  rules: ["Regla de pago principal"],
  systems: ["Pasarela de pago", "API de checkout"],
  existing_tests: ["test_checkout_happy_path"],
  historical_bugs: ["Bug de timeout en pagos internacionales"],
  risks: ["Riesgo de fraude en pagos"],
  citations: ["KB-001"],
};

const MOCK_PATH = {
  days: [
    { day: 1, items: ["Leer arquitectura de pagos", "Revisar flujos de checkout"] },
    { day: 2, items: ["Ejecutar suite de pruebas existente"] },
  ],
  citations: ["KB-002"],
};

const MOCK_ANSWER: { answer: string; citations: string[] } = {
  answer: "El flujo de checkout tiene 3 pasos principales.",
  citations: ["KB-003"],
};

describe("OnboardingPage — ¿Qué sabe el proyecto? (domainSummary)", () => {
  it("llama a domainSummary con el tema y renderiza regla + citación", async () => {
    (domainSummary as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_SUMMARY);

    renderWithClient(<OnboardingPage />);

    const topicInput = screen.getByPlaceholderText(/p\.ej\. pagos/i);
    fireEvent.change(topicInput, { target: { value: "pagos" } });

    const btn = screen.getByRole("button", { name: /¿Qué sabe el proyecto\?/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(domainSummary).toHaveBeenCalledWith("tok", { org_id: "o1", topic: "pagos" });
    });

    expect(await screen.findByText("· Regla de pago principal")).toBeInTheDocument();
    expect(screen.getByText("· KB-001")).toBeInTheDocument();
  });
});

describe("OnboardingPage — Ruta de aprendizaje (learningPath)", () => {
  it("llama a learningPath con el tema y renderiza un día", async () => {
    (learningPath as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_PATH);

    renderWithClient(<OnboardingPage />);

    const topicInput = screen.getByPlaceholderText(/p\.ej\. pagos/i);
    fireEvent.change(topicInput, { target: { value: "pagos" } });

    const btn = screen.getByRole("button", { name: /Ruta de aprendizaje/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(learningPath).toHaveBeenCalledWith("tok", { org_id: "o1", topic: "pagos" });
    });

    expect(await screen.findByText("Día 1")).toBeInTheDocument();
    expect(screen.getByText("· Leer arquitectura de pagos")).toBeInTheDocument();
    expect(screen.getByText("· KB-002")).toBeInTheDocument();
  });
});

describe("OnboardingPage — chat (askKnowledge)", () => {
  it("llama a askKnowledge y renderiza la respuesta con citaciones", async () => {
    (askKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_ANSWER);

    renderWithClient(<OnboardingPage />);

    const chatInput = screen.getByPlaceholderText(/¿Cómo funciona el flujo/i);
    fireEvent.change(chatInput, { target: { value: "¿Cómo funciona el checkout?" } });

    const btn = screen.getByRole("button", { name: /^Preguntar$/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(askKnowledge).toHaveBeenCalledWith("tok", {
        org_id: "o1",
        question: "¿Cómo funciona el checkout?",
      });
    });

    expect(await screen.findByText("El flujo de checkout tiene 3 pasos principales.")).toBeInTheDocument();
    expect(screen.getByText("· KB-003")).toBeInTheDocument();
  });
});

describe("OnboardingPage — degradación ante fallo del agente", () => {
  it("muestra toast.error cuando domainSummary rechaza y la página no se rompe", async () => {
    (domainSummary as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Servicio no disponible"));

    renderWithClient(<OnboardingPage />);

    const topicInput = screen.getByPlaceholderText(/p\.ej\. pagos/i);
    fireEvent.change(topicInput, { target: { value: "pagos" } });

    const btn = screen.getByRole("button", { name: /¿Qué sabe el proyecto\?/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Servicio no disponible");
    });

    // Page still renders correctly - button is still present
    expect(screen.getByRole("button", { name: /¿Qué sabe el proyecto\?/i })).toBeInTheDocument();
  });

  it("muestra toast.error cuando learningPath rechaza y la página no se rompe", async () => {
    (learningPath as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Timeout del agente"));

    renderWithClient(<OnboardingPage />);

    const topicInput = screen.getByPlaceholderText(/p\.ej\. pagos/i);
    fireEvent.change(topicInput, { target: { value: "auth" } });

    const btn = screen.getByRole("button", { name: /Ruta de aprendizaje/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Timeout del agente");
    });

    expect(screen.getByRole("button", { name: /Ruta de aprendizaje/i })).toBeInTheDocument();
  });
});

describe("OnboardingPage — empty state sin organización", () => {
  it("muestra mensaje de selecciona organización cuando no hay activeOrgId", () => {
    mockActiveOrg.value = null;

    renderWithClient(<OnboardingPage />);

    expect(screen.getByText(/selecciona una organización para comenzar el onboarding/i)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/p\.ej\. pagos/i)).not.toBeInTheDocument();
  });

  // I2: while loading, should NOT show "Selecciona organización"
  it("I2 — no muestra empty state de org mientras isLoading=true", () => {
    mockActiveOrg.value = "";
    mockActiveOrg.isLoading = true;

    renderWithClient(<OnboardingPage />);

    expect(screen.queryByText(/selecciona una organización para comenzar el onboarding/i)).not.toBeInTheDocument();
    expect(screen.getByText(/cargando…/i)).toBeInTheDocument();
  });
});
