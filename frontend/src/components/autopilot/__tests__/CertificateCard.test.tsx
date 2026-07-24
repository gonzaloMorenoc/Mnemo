// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  getCertificate: vi.fn(), generateCertificate: vi.fn(), getCertificatePdf: vi.fn(),
}));

import { getCertificate, getCertificatePdf } from "@/lib/api/endpoints";
import { toast } from "sonner";
import { CertificateCard } from "@/components/autopilot/CertificateCard";

afterEach(() => { vi.clearAllMocks(); cleanup(); });
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

describe("CertificateCard — sin_confirmar y manifiesto", () => {
  it("acta sin_confirmar: riesgo '—' y nota + manifiesto de canonical_json", async () => {
    (getCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({
      verdict: "sin_confirmar", risk_score: 0, signature: "SIGSIGSIGSIGSIGSIGSIGSIGSIGSIGSIG",
      canonical_json: {
        execution_manifest: { total: 128, passed: 120, failed: 5, skipped: 3, complete: true },
      },
    });
    renderWithClient(<CertificateCard runId="r1" />);
    expect(await screen.findByText("Sin confirmar")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/no prueba una ejecución completa/i)).toBeInTheDocument();
    expect(screen.getByText(/128 tests · 120 ✓ · 5 ✗ · 3 omitidos/)).toBeInTheDocument();
  });

  it("acta v2 (sin manifiesto): no rompe y muestra riesgo N/100", async () => {
    (getCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({
      verdict: "apto", risk_score: 12, signature: "SIGSIGSIGSIGSIGSIGSIGSIGSIGSIGSIG",
      canonical_json: {},
    });
    renderWithClient(<CertificateCard runId="r1" />);
    expect(await screen.findByText("Apto")).toBeInTheDocument();
    expect(screen.getByText("12/100")).toBeInTheDocument();
  });
});
