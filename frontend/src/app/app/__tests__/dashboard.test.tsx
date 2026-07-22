// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "t" }),
}));

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getGithubConfig: vi.fn(),
  listRepoTests: vi.fn(),
  listKnowledge: vi.fn(),
  getGaps: vi.fn(),
  listRuns: vi.fn(),
  getCalibrationMetrics: vi.fn(),
  listKnowledgeProposals: vi.fn(),
}));

import { useActiveOrg } from "@/components/providers/org-provider";
import {
  getGithubConfig,
  listRepoTests,
  listKnowledge,
  getGaps,
  listRuns,
  getCalibrationMetrics,
  listKnowledgeProposals,
} from "@/lib/api/endpoints";
import DashboardPage from "@/app/app/page";

function mockOperationalData() {
  (listRuns as ReturnType<typeof vi.fn>).mockResolvedValue([
    { id: "r1", project: "checkout-suite", source: "junit", commit_sha: "abc",
      created_at: "2026-07-22T10:00:00+00:00", verdict: "no-apto", risk_score: 20,
      failures: 3 },
  ]);
  (getCalibrationMetrics as ReturnType<typeof vi.fn>).mockResolvedValue({
    accuracy: 0.6, aciertos: 3, total: 5, familias_calibradas: 4, por_categoria: {},
  });
  (listKnowledgeProposals as ReturnType<typeof vi.fn>).mockResolvedValue([
    { id: "p1", status: "pending" },
  ]);
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("steps 1 y 2 done cuando github configurado y tests indexados", async () => {
    (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({
      activeOrgId: "o1",
      isLoading: false,
    });
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([
      { path: "a" },
    ]);
    (listKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    mockOperationalData();

    renderWithClient(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByTestId("step-done-1")).toBeDefined();
      expect(screen.getByTestId("step-done-2")).toBeDefined();
      expect(screen.getByTestId("step-todo-5")).toBeDefined();
    });

    expect(screen.getByTestId("step-todo-3")).toBeDefined();
    expect(screen.getByTestId("step-todo-4")).toBeDefined();
  });

  it("muestra los KPIs operativos: último veredicto, precisión, memoria y gaps", async () => {
    (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({
      activeOrgId: "o1",
      isLoading: false,
    });
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({ configured: true });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([{ path: "a" }]);
    (listKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue([{ id: "k1" }, { id: "k2" }]);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue([
      { kind: "regla_sin_test", title: "g", severity: "alta", affected: [], recommendation: "" },
    ]);
    mockOperationalData();

    renderWithClient(<DashboardPage />);

    await waitFor(() => {
      // último run con veredicto semántico (KPI + lista de runs recientes)
      expect(screen.getAllByText("No apto").length).toBeGreaterThan(0);
      expect(screen.getAllByText("checkout-suite").length).toBeGreaterThan(0);
      // precisión del motor
      expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
      // propuestas pendientes visibles
      expect(screen.getAllByText(/1 propuesta pendiente/i).length).toBeGreaterThan(0);
      // gaps con severidad alta destacada
      expect(screen.getAllByText(/1 de severidad alta/i).length).toBeGreaterThan(0);
      // checklist completo (pasos 1-4 done) → colapsado a una línea
      expect(screen.getAllByText(/Configuración completa/i).length).toBeGreaterThan(0);
      expect(screen.queryByTestId("step-todo-5")).toBeNull();
    });
  });

  it("muestra empty-state con enlace /app/org cuando no hay orgId", async () => {
    (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({
      activeOrgId: "",
      isLoading: false,
    });

    renderWithClient(<DashboardPage />);

    await waitFor(() => {
      const link = screen.getByRole("link", { name: /organización/i });
      expect(link.getAttribute("href")).toBe("/app/org");
    });
  });
});
