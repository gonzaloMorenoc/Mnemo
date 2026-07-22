// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  ingestReport: vi.fn(),
  listRuns: vi.fn(),
}));

import { RunSelector } from "@/components/autopilot/RunSelector";
import * as endpoints from "@/lib/api/endpoints";
import type { RunListItem } from "@/lib/api/types";

const RUN: RunListItem = {
  id: "r1", project: "checkout-suite", source: "junit", commit_sha: "abc",
  created_at: "2026-07-22T10:00:00+00:00", verdict: "no-apto", risk_score: 20,
  failures: 3,
};

function renderSelector(onRunId = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RunSelector orgId="o1" onRunId={onRunId} />
    </QueryClientProvider>,
  );
  return onRunId;
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("RunSelector — histórico de runs recientes", () => {
  it("lista los runs con proyecto, fallos y veredicto semántico", async () => {
    vi.mocked(endpoints.listRuns).mockResolvedValue([RUN]);
    renderSelector();
    await waitFor(() => expect(screen.getByText("checkout-suite")).toBeInTheDocument());
    expect(screen.getByText("3 fallos")).toBeInTheDocument();
    expect(screen.getByText("No apto")).toBeInTheDocument();
    expect(endpoints.listRuns).toHaveBeenCalledWith("tok", "o1", { limit: 8 });
  });

  it("clic en un run reciente selecciona su id (adiós pegar UUIDs)", async () => {
    vi.mocked(endpoints.listRuns).mockResolvedValue([RUN]);
    const onRunId = renderSelector();
    await screen.findByText("checkout-suite");
    fireEvent.click(screen.getByRole("button", { name: /checkout-suite/i }));
    expect(onRunId).toHaveBeenCalledWith("r1");
  });

  it("sin runs: mensaje de vacío con CTA implícito", async () => {
    vi.mocked(endpoints.listRuns).mockResolvedValue([]);
    renderSelector();
    await waitFor(() =>
      expect(screen.getByText(/Aún no hay runs/i)).toBeInTheDocument());
  });
});
