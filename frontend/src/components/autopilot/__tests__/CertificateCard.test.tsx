// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  getCertificate: vi.fn(), generateCertificate: vi.fn(), getCertificatePdf: vi.fn(),
}));

import { getCertificate, getCertificatePdf } from "@/lib/api/endpoints";
import { toast } from "sonner";
import { CertificateCard } from "@/components/autopilot/CertificateCard";

afterEach(() => vi.clearAllMocks());
function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CertificateCard PDF download", () => {
  it("descarga el PDF al pulsar el botón", async () => {
    (getCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({
      verdict: "apto", risk_score: 12, signature: "SIGSIGSIGSIGSIGSIGSIGSIGSIGSIGSIG" });
    (getCertificatePdf as ReturnType<typeof vi.fn>).mockResolvedValue(new Blob(["%PDF-"], { type: "application/pdf" }));
    const createUrl = vi.fn(() => "blob:x"); const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderWithClient(<CertificateCard runId="r1" />);
    const btn = await screen.findByRole("button", { name: /descargar pdf/i });
    fireEvent.click(btn);
    await waitFor(() => expect(getCertificatePdf).toHaveBeenCalledWith("tok", "r1"));
    await waitFor(() => expect(click).toHaveBeenCalled());
  });

  it("muestra toast de error si la descarga falla", async () => {
    (getCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({
      verdict: "apto", risk_score: 12, signature: "SIGSIGSIGSIGSIGSIGSIGSIGSIGSIGSIG" });
    (getCertificatePdf as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));
    renderWithClient(<CertificateCard runId="r1" />);
    const btn = await screen.findByRole("button", { name: /descargar pdf/i });
    fireEvent.click(btn);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });
});
