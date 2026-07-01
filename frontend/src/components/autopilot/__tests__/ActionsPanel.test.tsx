// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  getActions: vi.fn(), proposeActions: vi.fn(), approveAction: vi.fn(), rejectAction: vi.fn(),
}));

import { getActions, approveAction } from "@/lib/api/endpoints";
import { ActionsPanel } from "@/components/autopilot/ActionsPanel";

afterEach(() => { vi.clearAllMocks(); cleanup(); });

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ActionsPanel", () => {
  it("muestra solo las acciones del run y aprueba una propuesta", async () => {
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "ticket", summary: "Bug X", status: "proposed" },
      { id: "a2", triage_verdict_id: "v2", run_id: "OTHER", kind: "quarantine", summary: "Otro", status: "proposed" },
    ]);
    (approveAction as ReturnType<typeof vi.fn>).mockResolvedValue({ approved: true, materialized: true, artifact_ref: "https://gh/1" });
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);
    expect(await screen.findByText("Bug X")).toBeInTheDocument();
    expect(screen.queryByText("Otro")).not.toBeInTheDocument(); // filtrado por run_id
    fireEvent.click(screen.getByRole("button", { name: /aprobar/i }));
    await waitFor(() => expect(approveAction).toHaveBeenCalledWith("tok", "a1"));
  });

  it("muestra la etiqueta humana para el kind de acción, no el valor crudo", async () => {
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "quarantine", summary: "Test aislado", status: "proposed" },
      { id: "a2", triage_verdict_id: "v2", run_id: "r1", kind: "self_heal", summary: "Locator roto", status: "proposed" },
      { id: "a3", triage_verdict_id: "v3", run_id: "r1", kind: "ticket", summary: "Bug crítico", status: "proposed" },
    ]);
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);

    // Human labels visible
    expect(await screen.findByText("Cuarentena")).toBeInTheDocument();
    expect(screen.getByText("Auto-reparación")).toBeInTheDocument();
    expect(screen.getAllByText("Ticket").length).toBeGreaterThanOrEqual(1);

    // Raw kind values should not appear as standalone badge text
    expect(screen.queryByText("quarantine")).not.toBeInTheDocument();
    expect(screen.queryByText("self_heal")).not.toBeInTheDocument();
  });

  it("renderiza un InfoTooltip con aria-label en el encabezado Acciones", async () => {
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);

    // Wait for component to render
    expect(await screen.findByText(/Acciones/)).toBeInTheDocument();

    // InfoTooltip renders a button with aria-label
    const tooltipBtn = screen.getByRole("button", { name: /Qué es: Acciones de Nivel 2/i });
    expect(tooltipBtn).toBeInTheDocument();
  });
});
