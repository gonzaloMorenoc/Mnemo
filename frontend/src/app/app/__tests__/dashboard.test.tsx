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

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock("@/lib/api/endpoints", () => ({
  getGithubConfig: vi.fn(),
  listRepoTests: vi.fn(),
  listKnowledge: vi.fn(),
  getGaps: vi.fn(),
  listRuns: vi.fn(),
  getCalibrationMetrics: vi.fn(),
  listKnowledgeProposals: vi.fn(),
  getCertificate: vi.fn(),
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
  getCertificate,
} from "@/lib/api/endpoints";
import DashboardPage from "@/app/app/page";

function mockOperationalData() {
  (listRuns as ReturnType<typeof vi.fn>).mockResolvedValue([
    { id: "r1", project: "checkout-suite", source: "junit", commit_sha: "abc",
      created_at: "2026-07-22T10:00:00+00:00", verdict: "no-apto", risk_score: 20,
      failures: 3 },
  ]);
  (getCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({
    run_id: "r1", verdict: "no-apto", risk_score: 20, signature: "sig",
    canonical_json: { execution_manifest: { total: 40, passed: 37, failed: 3, skipped: 0, complete: true, source_format: "junit", artifact_sha256: "x" } },
  });
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
    (getCertificate as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("404"));

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
      expect(screen.getAllByText("No apto").length).toBeGreaterThan(0);
      expect(screen.getAllByText("checkout-suite").length).toBeGreaterThan(0);
      // héroe: manifiesto del acta del último run + CTA a Autopilot
      expect(screen.getByText(/40 tests · 37 ✓ · 3 ✗/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /Ver run/i })).toHaveAttribute("href", "/app/autopilot");
      // precisión del motor (gauge) al 60%
      expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/1 propuesta de la IA por revisar/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/1 de severidad alta/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Configuración completa/i).length).toBeGreaterThan(0);
      expect(screen.queryByTestId("step-todo-5")).toBeNull();
    });
  });

  it("héroe sin acta (getCertificate 404): muestra los fallos del run, no el manifiesto", async () => {
    (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({ activeOrgId: "o1", isLoading: false });
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({ configured: true });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([{ path: "a" }]);
    (listKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    mockOperationalData();
    (getCertificate as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("404"));

    renderWithClient(<DashboardPage />);

    await waitFor(() => {
      // "3 fallos" aparece tanto en el héroe como en la fila de "Runs recientes"
      // (mismo run mockeado) → ambiguo con getByText, se usa getAllByText.
      expect(screen.getAllByText(/3 fallos/).length).toBeGreaterThan(0);
      expect(screen.queryByText(/acta firmada/i)).toBeNull();
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
