// @vitest-environment jsdom
import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({
  verifyCertificate: vi.fn(async () => ({ valido: true })),
  getCertificatePubkey: vi.fn(async () => ({ algorithm: "ed25519", public_key_pem: "PEM" })),
}));

import { CertificateVerifier } from "@/components/verify/CertificateVerifier";
import { verifyCertificate } from "@/lib/api/endpoints";
import { ApiClientError } from "@/lib/api/client";
import { toast } from "sonner";

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

  it("enlace con contenido indecodificable (base64 inválido): mismo aviso ámbar", async () => {
    // Prefijo `#v1.` correcto, pero el contenido no es base64 válido: `decodeShare`
    // devuelve null (rama distinta a la del truncamiento, que sí decodifica pero
    // falla al parsear el JSON incompleto).
    renderConHash("#v1.!!!esto-no-es-base64!!!");
    expect(await screen.findByText(/enlace está incompleto/i)).toBeInTheDocument();
    expect(screen.queryByText(/ha sido alterada|no confíes/i)).toBeNull();
    expect(verifyCertificate).not.toHaveBeenCalled();
  });

  it("verificar a mano tras un enlace roto limpia el aviso ámbar (ya no aplica al texto nuevo)", async () => {
    // Enlace truncado: aparece el aviso ámbar.
    renderConHash(`#v1.${BLOB.slice(0, Math.floor(BLOB.length / 2))}`);
    expect(await screen.findByText(/enlace está incompleto/i)).toBeInTheDocument();

    // El usuario pega a mano un acta distinta (JSON inválido) y verifica.
    fireEvent.change(screen.getByLabelText(/Acta en formato JSON/i), {
      target: { value: "esto no es json" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Verificar firma/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // El aviso del enlace ya no aplica: el acta en pantalla no vino de un enlace.
    expect(screen.queryByText(/enlace está incompleto/i)).toBeNull();
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

  it("error 4xx del backend (acta aplanada, sin canonical_json): muestra el motivo real, sin hablar de conexión ni de manipulación", async () => {
    // Un 422 de Pydantic no es un fallo de transporte: el servicio SÍ respondió,
    // solo que rechazó el cuerpo. Atribuirlo a "no hay conexión" es una causa falsa.
    (verifyCertificate as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiClientError("El campo 'canonical_json' es obligatorio.", 422),
    );
    renderConHash(`#v1.${BLOB}`);

    expect(await screen.findByText(/no se pudo comprobar la firma/i)).toBeInTheDocument();
    expect(screen.getByText(/El campo 'canonical_json' es obligatorio\./)).toBeInTheDocument();
    expect(screen.queryByText(/no hay conexión/i)).toBeNull();
    expect(screen.queryByText(/alterada|no confíes/i)).toBeNull();
  });

  it("orden visual: por enlace el sello va arriba y el acta queda plegada; verificar a mano restaura el orden normal", async () => {
    // Un test anterior puede haber dejado el mock en rechazo/inválido
    // (mockResolvedValue/mockRejectedValue sobreviven a clearAllMocks): este
    // test necesita el camino feliz explícitamente.
    (verifyCertificate as ReturnType<typeof vi.fn>).mockResolvedValue({ valido: true });
    const { container } = renderConHash(`#v1.${BLOB}`);

    // Llega por enlace: el sello (autenticidad ya validada) se ve arriba, y el
    // acta queda a un clic dentro de un <details>, no como formulario abierto.
    expect(await screen.findByText(/acta auténtica/i)).toBeInTheDocument();
    expect(container.querySelector("details")).not.toBeNull();

    // El usuario pega otra acta a mano y la verifica: esa procedencia "por
    // enlace" ya no aplica al texto en pantalla, y el reseteo debe notarse en
    // la disposición, no solo en el aviso ámbar.
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: ACTA } });
    fireEvent.click(screen.getByRole("button", { name: /Verificar firma/i }));

    await waitFor(() => expect(verifyCertificate).toHaveBeenCalledTimes(2));
    await screen.findByText(/acta auténtica/i);
    // Disposición normal: el formulario ya no está plegado en un <details>.
    expect(container.querySelector("details")).toBeNull();
  });
});
