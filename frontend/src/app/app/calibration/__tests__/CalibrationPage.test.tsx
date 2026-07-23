// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({
  getCalibrationMetrics: vi.fn(),
  getOrganizations: vi.fn().mockResolvedValue([{ id: "org-1", name: "Org" }]),
}));

import { getCalibrationMetrics } from "@/lib/api/endpoints";
import { OrgProvider } from "@/components/providers/org-provider";
import CalibrationPage from "@/app/app/calibration/page";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><OrgProvider>{ui}</OrgProvider></QueryClientProvider>);
}

describe("CalibrationPage", () => {
  it("muestra la precisión y el desglose", async () => {
    (getCalibrationMetrics as ReturnType<typeof vi.fn>).mockResolvedValue({
      total: 3, aciertos: 2, accuracy: 0.6667, familias_calibradas: 2, por_categoria: { flaky: 2, real: 1 } });
    renderWithClient(<CalibrationPage />);
    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/2 familias con etiqueta humana/i)).toBeInTheDocument();
  });
});
