// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/lib/api/endpoints", () => ({
  verifyCertificate: vi.fn(async () => ({ valido: true })),
  getCertificatePubkey: vi.fn(async () => ({ algorithm: "ed25519", public_key_pem: "PEM" })),
}));

import VerifyPage from "@/app/verify/page";
import { verifyCertificate } from "@/lib/api/endpoints";

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <VerifyPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("VerifyPage — verifica el acta sin re-serializar el JSON", () => {
  it("envía a verifyCertificate el TEXTO CRUDO pegado, preservando 0.0 (no lo convierte en 0)", async () => {
    renderWithClient();
    // Acta con un decimal 'redondo': Python firma "0.0"; si el navegador lo
    // re-serializa (JSON.parse -> JSON.stringify) lo colapsa a 0 y la firma falla.
    const raw =
      '{"canonical_json":{"schema":"mnemo.cert.v2","self_eval":{"engine_calibration":{"tenant_accuracy":0.0}}},"signature":"sig"}';

    fireEvent.change(screen.getByLabelText(/Acta en formato JSON/i), {
      target: { value: raw },
    });
    fireEvent.click(screen.getByRole("button", { name: /Verificar firma/i }));

    await waitFor(() => expect(verifyCertificate).toHaveBeenCalledTimes(1));
    // Debe recibir el string EXACTO, no un objeto ya parseado y re-serializado.
    expect(verifyCertificate).toHaveBeenCalledWith(raw);
  });
});
