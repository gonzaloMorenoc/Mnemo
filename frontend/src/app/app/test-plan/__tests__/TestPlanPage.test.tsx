// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));

const mockActiveOrgId: { value: string | null } = { value: "o1" };

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: () => ({
    activeOrgId: mockActiveOrgId.value,
    orgs: mockActiveOrgId.value
      ? [{ id: "o1", name: "Test Org", join_code: "ABC", role: "owner", created_at: null }]
      : [],
    setActiveOrgId: vi.fn(),
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api/endpoints", () => ({
  generateTestPlan: vi.fn(),
  exportTestPlanXray: vi.fn(),
}));

import { generateTestPlan, exportTestPlanXray } from "@/lib/api/endpoints";
import { toast } from "sonner";
import TestPlanPage from "@/app/app/test-plan/page";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
  mockActiveOrgId.value = "o1"; // reset to default org
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const MOCK_PLAN = {
  summary: "QA plan for checkout",
  systems: ["web", "api"],
  risks: ["payment failure"],
  preconditions: ["user logged in"],
  test_data: ["card 4242424242424242"],
  cases: [
    {
      title: "Happy path checkout",
      level: "integration",
      priority: "high",
      automatable: true,
      steps: ["add item to cart", "checkout"],
      expected: "order confirmed",
    },
  ],
  gaps: ["no mobile coverage"],
  open_questions: ["what about 3DS?"],
  citations: ["HU-42"],
};

const MOCK_RESULT = { plan: MOCK_PLAN, citations: ["HU-42"] };

describe("TestPlanPage — generación desde textarea", () => {
  it("llama a generateTestPlan con el FormData incluyendo hu_text y case_format, y renderiza el plan con summary, caso y cita", async () => {
    (generateTestPlan as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_RESULT);

    renderWithClient(<TestPlanPage />);

    // Select "Texto" mode (default) — the textarea should already be visible
    const textarea = screen.getByPlaceholderText(/pega aquí la historia/i);
    fireEvent.change(textarea, { target: { value: "Como usuario quiero pagar" } });

    // Click Generar
    const genBtn = screen.getByRole("button", { name: /^Generar$/i });
    fireEvent.click(genBtn);

    await waitFor(() => {
      expect(generateTestPlan).toHaveBeenCalledWith(
        "tok",
        expect.any(FormData),
      );
    });

    const [, form] = (generateTestPlan as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(form.get("org_id")).toBe("o1");
    expect(form.get("case_format")).toBe("steps");
    expect(form.get("hu_text")).toBe("Como usuario quiero pagar");

    // Plan rendered
    expect(await screen.findByDisplayValue("QA plan for checkout")).toBeInTheDocument();
    expect(screen.getByText("Happy path checkout")).toBeInTheDocument();
    expect(screen.getByText("· HU-42")).toBeInTheDocument();
  });
});

describe("TestPlanPage — editar campo y Re-generar", () => {
  it("tras editar el resumen, Re-generar vuelve a llamar generateTestPlan y actualiza el plan", async () => {
    (generateTestPlan as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_RESULT);

    renderWithClient(<TestPlanPage />);

    // Generate first
    const textarea = screen.getByPlaceholderText(/pega aquí la historia/i);
    fireEvent.change(textarea, { target: { value: "HU original" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generar$/i }));

    await waitFor(() => expect(generateTestPlan).toHaveBeenCalledTimes(1));
    expect(await screen.findByDisplayValue("QA plan for checkout")).toBeInTheDocument();

    // Edit the summary
    const summaryField = screen.getByDisplayValue("QA plan for checkout");
    fireEvent.change(summaryField, { target: { value: "Resumen modificado" } });
    expect(screen.getByDisplayValue("Resumen modificado")).toBeInTheDocument();

    // Re-generate (the plan result resets back to the mock)
    const regenBtn = screen.getByRole("button", { name: /re-generar/i });
    fireEvent.click(regenBtn);

    await waitFor(() => expect(generateTestPlan).toHaveBeenCalledTimes(2));
    // After re-generate the summary should be reset to mock value
    expect(await screen.findByDisplayValue("QA plan for checkout")).toBeInTheDocument();
  });
});

describe("TestPlanPage — importar a Jira (Xray)", () => {
  it("llama a exportTestPlanXray y muestra toast con las keys retornadas", async () => {
    (generateTestPlan as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_RESULT);
    (exportTestPlanXray as ReturnType<typeof vi.fn>).mockResolvedValue({ "TC-1": "XR-10001" });

    renderWithClient(<TestPlanPage />);

    // First generate the plan
    const textarea = screen.getByPlaceholderText(/pega aquí la historia/i);
    fireEvent.change(textarea, { target: { value: "HU de prueba" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generar$/i }));

    await waitFor(() => expect(generateTestPlan).toHaveBeenCalled());
    await screen.findByText("Happy path checkout");

    // Click Importar a Jira (Xray)
    const xrayBtn = screen.getByRole("button", { name: /importar a jira/i });
    fireEvent.click(xrayBtn);

    await waitFor(() => {
      expect(exportTestPlanXray).toHaveBeenCalledWith(
        "tok",
        expect.objectContaining({
          org_id: "o1",
          case_format: "steps",
        }),
      );
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("TC-1"));
    });
  });

  it("muestra toast.error('Configura Xray') cuando exportTestPlanXray falla", async () => {
    (generateTestPlan as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_RESULT);
    (exportTestPlanXray as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("503"));

    renderWithClient(<TestPlanPage />);

    const textarea = screen.getByPlaceholderText(/pega aquí la historia/i);
    fireEvent.change(textarea, { target: { value: "HU fallida" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generar$/i }));

    await waitFor(() => expect(generateTestPlan).toHaveBeenCalled());
    await screen.findByText("Happy path checkout");

    fireEvent.click(screen.getByRole("button", { name: /importar a jira/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Configura Xray");
    });
  });
});

describe("TestPlanPage — generar falla sin romper la página", () => {
  it("muestra toast.error si generateTestPlan rechaza, y la página sigue operativa", async () => {
    (generateTestPlan as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("Error de red"));

    renderWithClient(<TestPlanPage />);

    const textarea = screen.getByPlaceholderText(/pega aquí la historia/i);
    fireEvent.change(textarea, { target: { value: "HU con error" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generar$/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Error de red");
    });

    // Page is still rendered — generate button still visible
    expect(screen.getByRole("button", { name: /^Generar$/i })).toBeInTheDocument();
  });
});

describe("TestPlanPage — empty state sin organización", () => {
  it("muestra mensaje de selecciona organización cuando no hay activeOrgId", () => {
    mockActiveOrgId.value = null;

    renderWithClient(<TestPlanPage />);

    expect(screen.getByText(/selecciona una organización para generar/i)).toBeInTheDocument();
    // The form inputs are NOT present when no org
    expect(screen.queryByPlaceholderText(/pega aquí la historia/i)).not.toBeInTheDocument();
  });
});

describe("TestPlanPage — Exportar Markdown", () => {
  const mockCreateObjectURL = vi.fn().mockReturnValue("blob:fake");
  const mockRevokeObjectURL = vi.fn();
  const mockClick = vi.fn();

  beforeAll(() => {
    global.URL.createObjectURL = mockCreateObjectURL;
    global.URL.revokeObjectURL = mockRevokeObjectURL;
  });

  it("llama a URL.createObjectURL con un Blob y luego a URL.revokeObjectURL al pulsar Exportar Markdown", async () => {
    (generateTestPlan as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_RESULT);

    const actualCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        const a = actualCreateElement(tag) as HTMLAnchorElement;
        a.click = mockClick;
        return a;
      }
      return actualCreateElement(tag);
    });

    renderWithClient(<TestPlanPage />);

    // Generate a plan first
    const textarea = screen.getByPlaceholderText(/pega aquí la historia/i);
    fireEvent.change(textarea, { target: { value: "Como usuario quiero exportar" } });
    fireEvent.click(screen.getByRole("button", { name: /^Generar$/i }));

    await waitFor(() => expect(generateTestPlan).toHaveBeenCalled());
    await screen.findByText("Happy path checkout");

    // Click Exportar Markdown
    const exportBtn = screen.getByRole("button", { name: /exportar markdown/i });
    fireEvent.click(exportBtn);

    expect(mockCreateObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    expect(mockRevokeObjectURL).toHaveBeenCalled();
  });
});
