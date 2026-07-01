// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({ getBriefing: vi.fn() }));

import { getBriefing } from "@/lib/api/endpoints";
import { BriefingCard } from "@/components/autopilot/BriefingCard";

afterEach(() => vi.clearAllMocks());
function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("BriefingCard", () => {
  it("muestra el resumen ejecutivo del run", async () => {
    (getBriefing as ReturnType<typeof vi.fn>).mockResolvedValue({
      verdict: "apto-con-reservas", summary: "Checkout falla por un 500.",
      recommendation: "Revisar el parche propuesto.", highlights: ["1 defecto real"], citations: ["family:f1"] });
    renderWithClient(<BriefingCard runId="r1" />);
    expect(await screen.findByText("Checkout falla por un 500.")).toBeInTheDocument();
    expect(screen.getByText("apto-con-reservas")).toBeInTheDocument();
    expect(screen.getByText("Revisar el parche propuesto.")).toBeInTheDocument();
  });

  it("muestra un fallback discreto si el briefing falla (no rompe)", async () => {
    (getBriefing as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("llm down"));
    renderWithClient(<BriefingCard runId="r1" />);
    expect(await screen.findByText(/resumen no disponible/i)).toBeInTheDocument();
  });

  it("muestra Skeleton (data-testid=briefing-loading-skeleton) en estado de carga — nunca el texto plano", () => {
    // Never resolves → stays in loading state
    (getBriefing as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));
    renderWithClient(<BriefingCard runId="r1" />);
    expect(screen.getByTestId("briefing-loading-skeleton")).toBeInTheDocument();
    expect(screen.queryByText(/cargando resumen/i)).not.toBeInTheDocument();
  });
});
