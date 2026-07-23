// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  getCertificatePubkey: vi.fn().mockRejectedValue(new Error("no pubkey")),
  verifyCertificate: vi.fn(),
}));

import AppVerifyPage from "@/app/app/verify/page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AppVerifyPage />
    </QueryClientProvider>,
  );
}

afterEach(cleanup);

describe("/app/verify (dentro del shell)", () => {
  it("tiene su propio h1 y el verificador, sin el back-link a la home", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Verificar acta", level: 1 })).toBeInTheDocument();
    // El núcleo de verificación está presente
    expect(screen.getByRole("button", { name: /Verificar firma/i })).toBeInTheDocument();
    // NO debe haber "Volver al inicio" (eso es de la página pública)
    expect(screen.queryByText(/Volver al inicio/i)).toBeNull();
  });

  it("enlaza a la versión pública /verify para compartir sin cuenta", () => {
    renderPage();
    expect(screen.getByRole("link", { name: "/verify" })).toHaveAttribute("href", "/verify");
  });
});
