// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  getActions: vi.fn(), proposeActions: vi.fn(), approveAction: vi.fn(), rejectAction: vi.fn(),
}));

import { getActions, approveAction, rejectAction } from "@/lib/api/endpoints";
import { ActionsPanel } from "@/components/autopilot/ActionsPanel";

// Radix UI pointer/scroll APIs not available in jsdom
beforeEach(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => undefined;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => undefined;
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
});

afterEach(() => { vi.clearAllMocks(); cleanup(); });

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ActionsPanel", () => {
  it("muestra solo las acciones del run", async () => {
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "ticket", summary: "Bug X", status: "proposed" },
      { id: "a2", triage_verdict_id: "v2", run_id: "OTHER", kind: "quarantine", summary: "Otro", status: "proposed" },
    ]);
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);
    expect(await screen.findByText("Bug X")).toBeInTheDocument();
    expect(screen.queryByText("Otro")).not.toBeInTheDocument(); // filtrado por run_id
  });

  it("pulsar Aprobar abre el diálogo de confirmación y la mutación NO se ejecuta aún", async () => {
    const user = userEvent.setup();
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "ticket", summary: "Bug X", status: "proposed" },
    ]);
    (approveAction as ReturnType<typeof vi.fn>).mockResolvedValue({ approved: true });
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);

    // Wait for action to appear
    expect(await screen.findByText("Bug X")).toBeInTheDocument();

    // Click Aprobar button
    await user.click(screen.getByRole("button", { name: /aprobar/i }));

    // Dialog should be open — look for confirmation dialog content
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();

    // Mutation has NOT been called yet
    expect(approveAction).not.toHaveBeenCalled();
  });

  it("approve.mutate se llama SOLO tras confirmar en el diálogo", async () => {
    const user = userEvent.setup();
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "self_heal", summary: "Locator roto", status: "proposed" },
    ]);
    (approveAction as ReturnType<typeof vi.fn>).mockResolvedValue({ approved: true });

    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);
    expect(await screen.findByText("Locator roto")).toBeInTheDocument();

    // Open dialog
    await user.click(screen.getByRole("button", { name: /aprobar/i }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();

    // Confirm
    await user.click(screen.getByRole("button", { name: /confirmar/i }));

    await waitFor(() => expect(approveAction).toHaveBeenCalledWith("tok", "a1"));
  });

  it("cancelar en el diálogo de aprobación NO llama a approve.mutate", async () => {
    const user = userEvent.setup();
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "quarantine", summary: "Test X", status: "proposed" },
    ]);
    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);
    expect(await screen.findByText("Test X")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /aprobar/i }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancelar/i }));

    await waitFor(() => expect(approveAction).not.toHaveBeenCalled());
  });

  it("rechazar también abre diálogo y reject.mutate se llama solo tras confirmar", async () => {
    const user = userEvent.setup();
    (getActions as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "a1", triage_verdict_id: "v1", run_id: "r1", kind: "ticket", summary: "Bug Y", status: "proposed" },
    ]);
    (rejectAction as ReturnType<typeof vi.fn>).mockResolvedValue({ rejected: true });

    renderWithClient(<ActionsPanel runId="r1" orgId="org-1" />);
    expect(await screen.findByText("Bug Y")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /rechazar/i }));
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();
    expect(rejectAction).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /confirmar/i }));
    await waitFor(() => expect(rejectAction).toHaveBeenCalledWith("tok", "a1"));
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
    const tooltipBtn = screen.getByRole("button", { name: /Qué son: acciones correctivas/i });
    expect(tooltipBtn).toBeInTheDocument();
  });
});
