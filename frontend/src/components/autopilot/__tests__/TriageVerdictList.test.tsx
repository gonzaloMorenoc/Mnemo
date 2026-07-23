// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({ getTriageVerdicts: vi.fn() }));

import { getTriageVerdicts } from "@/lib/api/endpoints";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";

afterEach(() => { vi.clearAllMocks(); cleanup(); });

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("TriageVerdictList", () => {
  it("muestra los veredictos con etiqueta humana (no el valor crudo) y la regla aplicada", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "v1", failure_id: "f1", category: "real", confidence: 0.85,
        rule_applied: "R4_real_recurrent", requires_approval: false, llm_assisted: false, status: "resolved" },
    ]);
    renderWithClient(<TriageVerdictList runId="r1" />);
    // Human label visible (may appear in legend + badge)
    const falloRealEls = await screen.findAllByText("Fallo real");
    expect(falloRealEls.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/R4_real_recurrent/)).toBeInTheDocument();
    // Raw "real" value should not appear as text
    expect(screen.queryByText("real")).not.toBeInTheDocument();
  });

  it("muestra etiquetas humanas para todas las categorías en la leyenda de colores", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderWithClient(<TriageVerdictList runId="r1" />);
    // The color legend renders all category labels
    expect(await screen.findAllByText("Fallo real")).not.toHaveLength(0);
    expect(screen.getByText("Flaky")).toBeInTheDocument();
    expect(screen.getByText("Mantenimiento")).toBeInTheDocument();
    expect(screen.getByText("Infraestructura")).toBeInTheDocument();  // etiqueta unificada con CategoryBadge
    expect(screen.getByText("Sin etiquetar")).toBeInTheDocument();
  });

  it("renderiza un InfoTooltip con aria-label en el encabezado de triaje", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderWithClient(<TriageVerdictList runId="r1" />);
    expect(await screen.findByText(/Veredictos de triaje/)).toBeInTheDocument();
    // InfoTooltip renders a button with aria-label "Qué es: triaje"
    const tooltipBtn = screen.getByRole("button", { name: "Qué es: triaje" });
    expect(tooltipBtn).toBeInTheDocument();
  });
});
