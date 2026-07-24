// @vitest-environment jsdom
import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, cleanup, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  verifyCertificate: vi.fn(async () => ({ valido: true })),
  getCertificatePubkey: vi.fn(async () => ({ algorithm: "ed25519", public_key_pem: "PEM" })),
}));

import { CertificateVerifier } from "@/components/verify/CertificateVerifier";
import { verifyCertificate } from "@/lib/api/endpoints";

const ACTA =
  '{"canonical_json":{"schema":"mnemo.cert.v3","verdict":"apto","identity":{"project":"checkout-suite"},"x":0.0},"signature":"sig"}';
const BLOB = Buffer.from(ACTA, "utf8").toString("base64url").replace(/=+$/, "");

function renderConHash(hash: string, strict = false) {
  window.location.hash = hash;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (
    <QueryClientProvider client={client}>
      <CertificateVerifier />
    </QueryClientProvider>
  );
  return render(strict ? <StrictMode>{ui}</StrictMode> : ui);
}

afterEach(() => { window.location.hash = ""; vi.clearAllMocks(); cleanup(); });

describe("CertificateVerifier — llegada por enlace", () => {
  it("auto-verifica enviando el acta VERBATIM (el 0.0 no se convierte en 0)", async () => {
    renderConHash(`#v1.${BLOB}`);
    await waitFor(() => expect(verifyCertificate).toHaveBeenCalledWith(ACTA));
  });

  it("no verifica dos veces aunque StrictMode monte el efecto dos veces", async () => {
    renderConHash(`#v1.${BLOB}`, true);
    await waitFor(() => expect(verifyCertificate).toHaveBeenCalled());
    expect(verifyCertificate).toHaveBeenCalledTimes(1);
  });

  it("enlace truncado: avisa de que se cortó y NO acusa de acta alterada", async () => {
    // Un base64 cortado por la mitad: decodifica a un JSON incompleto.
    renderConHash(`#v1.${BLOB.slice(0, Math.floor(BLOB.length / 2))}`);
    expect(await screen.findByText(/enlace está incompleto/i)).toBeInTheDocument();
    expect(screen.queryByText(/ha sido alterada|no confíes/i)).toBeNull();
    expect(verifyCertificate).not.toHaveBeenCalled();
  });

  it("sin hash se comporta como siempre: no verifica nada al montar", async () => {
    renderConHash("");
    await screen.findByLabelText(/Acta en formato JSON/i);
    expect(verifyCertificate).not.toHaveBeenCalled();
  });

  it("REGLA DE CONFIANZA: firma inválida no pinta ni un campo del acta", async () => {
    // El acta viene de una URL: quien la construya puede poner el proyecto y el
    // veredicto que quiera. Hasta que la firma valide, no se muestra nada suyo.
    (verifyCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({ valido: false });
    renderConHash(`#v1.${BLOB}`);

    expect(await screen.findByText(/no confíes en su contenido/i)).toBeInTheDocument();
    expect(screen.queryByText("checkout-suite")).toBeNull();
    expect(screen.queryByText("Apto")).toBeNull();
  });

  it("error de red: estado neutro, no acusa de acta alterada", async () => {
    (verifyCertificate as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("offline"));
    renderConHash(`#v1.${BLOB}`);

    expect(await screen.findByText(/no se pudo comprobar la firma/i)).toBeInTheDocument();
    expect(screen.queryByText(/no confíes en su contenido/i)).toBeNull();
  });
});
