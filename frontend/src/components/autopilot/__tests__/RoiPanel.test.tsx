// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({ getTriageVerdicts: vi.fn() }));

import { getTriageVerdicts } from "@/lib/api/endpoints";
import { RoiPanel } from "@/components/autopilot/RoiPanel";

afterEach(() => vi.clearAllMocks());
function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("RoiPanel", () => {
  it("calcula horas ahorradas de los auto-triados y muestra el supuesto + 0€", async () => {
    // 4 auto-triados (requires_approval false, category != unknown) + 1 que requiere approval + 1 unknown
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "1", category: "flaky", requires_approval: false },
      { id: "2", category: "maintenance", requires_approval: false },
      { id: "3", category: "real", requires_approval: false },
      { id: "4", category: "flaky", requires_approval: false },
      { id: "5", category: "real", requires_approval: true },
      { id: "6", category: "unknown", requires_approval: true },
    ]);
    renderWithClient(<RoiPanel runId="r1" />);
    expect(await screen.findByText(/1\.0\s*h/)).toBeInTheDocument();   // 4 × 15 / 60 = 1.0 h
    expect(screen.getByText(/15 min/)).toBeInTheDocument();            // el supuesto visible
    expect(screen.getByText(/0\s*€/)).toBeInTheDocument();            // coste 0€
  });

  it("no rompe con 0 veredictos", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    renderWithClient(<RoiPanel runId="r1" />);
    expect(await screen.findByText(/0\.0\s*h/)).toBeInTheDocument();
  });
});
