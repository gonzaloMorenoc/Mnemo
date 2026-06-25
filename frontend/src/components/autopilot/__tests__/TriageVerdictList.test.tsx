// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({ getTriageVerdicts: vi.fn() }));

import { getTriageVerdicts } from "@/lib/api/endpoints";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("TriageVerdictList", () => {
  it("muestra los veredictos con su categoría", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "v1", failure_id: "f1", category: "real", confidence: 0.85,
        rule_applied: "R4_real_recurrent", requires_approval: false, llm_assisted: false, status: "resolved" },
    ]);
    renderWithClient(<TriageVerdictList runId="r1" />);
    expect(await screen.findByText("real")).toBeInTheDocument();
    expect(screen.getByText(/R4_real_recurrent/)).toBeInTheDocument();
  });
});
