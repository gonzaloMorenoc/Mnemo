// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// ─── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));

const mockActiveOrg: { value: string | null; isLoading: boolean } = {
  value: "o1",
  isLoading: false,
};

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: () => ({
    activeOrgId: mockActiveOrg.value,
    isLoading: mockActiveOrg.isLoading,
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// react-flow is heavy and jsdom can't render it — stub with a minimal div
vi.mock("@/components/graph/knowledge-graph-view", () => ({
  KnowledgeGraphView: ({ graph }: { graph: { nodes: unknown[] } }) => (
    <div data-testid="knowledge-graph-view">
      nodes:{graph.nodes.length}
    </div>
  ),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getGraph: vi.fn(),
  getGaps: vi.fn(),
}));

import { getGraph, getGaps } from "@/lib/api/endpoints";
import { toast } from "sonner";
import GraphPage from "@/app/app/graph/page";

// ─── helpers ──────────────────────────────────────────────────────────────────

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
  mockActiveOrg.value = "o1";
  mockActiveOrg.isLoading = false;
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

// ─── fixtures ─────────────────────────────────────────────────────────────────

const MOCK_GRAPH = {
  nodes: [
    { id: "n1", type: "knowledge" as const, label: "Regla de pago", kind: "regla_negocio" },
    { id: "n2", type: "domain" as const, label: "Pagos" },
  ],
  edges: [{ source: "n1", target: "n2", relation: "pertenece" as const }],
};

const MOCK_GAPS = [
  {
    kind: "knowledge",
    title: "Sin cobertura en flujo de reembolso",
    severity: "alta" as const,
    affected: ["pagos", "reembolso"],
    recommendation: "Documentar el flujo de reembolso con al menos 3 reglas",
  },
  {
    kind: "knowledge",
    title: "Gap en autenticación",
    severity: "media" as const,
    affected: ["auth"],
    recommendation: "Agregar regla sobre expiración de tokens",
  },
  {
    kind: "defect",
    title: "Defecto menor en logs",
    severity: "baja" as const,
    affected: ["logs"],
    recommendation: "Revisar formato de logs de error",
  },
];

// ─── tests ────────────────────────────────────────────────────────────────────

describe("GraphPage — renderiza grafo y panel de gaps", () => {
  it("llama a getGraph y getGaps con el org_id correcto", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GRAPH);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GAPS);

    renderWithClient(<GraphPage />);

    await waitFor(() => {
      expect(getGraph).toHaveBeenCalledWith("tok", { org_id: "o1" });
      expect(getGaps).toHaveBeenCalledWith("tok", { org_id: "o1" });
    });
  });

  it("renderiza el contenedor del grafo (KnowledgeGraphView)", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GRAPH);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GAPS);

    renderWithClient(<GraphPage />);

    const view = await screen.findByTestId("knowledge-graph-view");
    expect(view).toBeInTheDocument();
  });

  it("renderiza el título de un gap con su badge de severidad", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GRAPH);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GAPS);

    renderWithClient(<GraphPage />);

    expect(
      await screen.findByText("Sin cobertura en flujo de reembolso"),
    ).toBeInTheDocument();

    expect(screen.getByTestId("gap-severity-alta")).toBeInTheDocument();
  });

  it("muestra la recomendación del gap", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GRAPH);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GAPS);

    renderWithClient(<GraphPage />);

    expect(
      await screen.findByText(
        "Documentar el flujo de reembolso con al menos 3 reglas",
      ),
    ).toBeInTheDocument();
  });
});

describe("GraphPage — ordena gaps por severidad alta→media→baja", () => {
  it("lista alta antes que media antes que baja", async () => {
    // Provide gaps in reverse order to prove sorting
    const reversed = [...MOCK_GAPS].reverse();
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GRAPH);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue(reversed);

    renderWithClient(<GraphPage />);

    const allBadges = await screen.findAllByTestId(/^gap-severity-/);
    const labels = allBadges.map((el) => el.textContent);
    expect(labels).toEqual(["alta", "media", "baja"]);
  });
});

describe("GraphPage — empty state sin organización", () => {
  it("muestra mensaje de selecciona organización cuando no hay activeOrgId", () => {
    mockActiveOrg.value = null;

    renderWithClient(<GraphPage />);

    expect(
      screen.getByText(/selecciona una organización para ver el Knowledge Graph/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("knowledge-graph-view")).not.toBeInTheDocument();
  });

  it("no muestra empty state mientras isLoading=true", () => {
    mockActiveOrg.value = null;
    mockActiveOrg.isLoading = true;

    renderWithClient(<GraphPage />);

    expect(
      screen.queryByText(/selecciona una organización/i),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/cargando…/i)).toBeInTheDocument();
  });
});

describe("GraphPage — grafo vacío", () => {
  it("muestra 'Aún no hay conocimiento suficiente' cuando el grafo no tiene nodos", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue({ nodes: [], edges: [] });
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderWithClient(<GraphPage />);

    expect(
      await screen.findByText(/aún no hay conocimiento suficiente/i),
    ).toBeInTheDocument();
  });
});

describe("GraphPage — degradación ante errores de query", () => {
  it("llama a toast.error cuando getGraph rechaza y la página no se rompe", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Error al cargar el grafo"),
    );
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderWithClient(<GraphPage />);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Error al cargar el grafo");
    });

    // Page still renders — no crash
    expect(screen.getByText("Knowledge Graph")).toBeInTheDocument();
  });

  it("llama a toast.error cuando getGaps rechaza y la página no se rompe", async () => {
    (getGraph as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_GRAPH);
    (getGaps as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Error al cargar los gaps"),
    );

    renderWithClient(<GraphPage />);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Error al cargar los gaps");
    });

    expect(screen.getByText("Knowledge Graph")).toBeInTheDocument();
  });
});
