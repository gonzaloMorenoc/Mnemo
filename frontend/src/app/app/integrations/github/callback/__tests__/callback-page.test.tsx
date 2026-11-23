// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ replace, push: vi.fn() }),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: () => ({ activeOrgId: "o-activa", isLoading: false }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  saveGithubConfig: vi.fn(),
}));

import { saveGithubConfig } from "@/lib/api/endpoints";
import { ApiClientError } from "@/lib/api/client";
import { readPendingGithubLink, savePendingGithubLink } from "@/lib/github/link";
import { SUCCESS_REDIRECT_MS } from "@/components/integrations/GithubCallbackView";
import GithubCallbackPage from "@/app/app/integrations/github/callback/page";

const OK_RESPONSE = { configured: true, repo_full_name: "acme/web", installation_id: "42" };

function setQuery(search: string) {
  window.history.replaceState({}, "", `/app/integrations/github/callback${search}`);
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GithubCallbackPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  savePendingGithubLink({ orgId: "o1", repoFullName: "acme/web", state: "st.mac" });
  setQuery("?installation_id=42&code=c0de&state=st.mac&setup_action=install");
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Callback de GitHub — éxito", () => {
  it("manda installation_id, state y code con la org y el repo guardados, y vuelve a Integraciones", async () => {
    vi.mocked(saveGithubConfig).mockResolvedValue(OK_RESPONSE);
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(/GitHub conectado/i);
    expect(saveGithubConfig).toHaveBeenCalledTimes(1);
    expect(saveGithubConfig).toHaveBeenCalledWith("tok", {
      org_id: "o1",
      installation_id: "42",
      repo_full_name: "acme/web",
      state: "st.mac",
      code: "c0de",
    });
    expect(readPendingGithubLink()).toBeNull();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/app/integrations"), {
      timeout: SUCCESS_REDIRECT_MS + 1000,
    });
  });

  it("sin vinculación guardada en el navegador pide el repositorio y usa la org activa", async () => {
    window.sessionStorage.clear();
    vi.mocked(saveGithubConfig).mockResolvedValue(OK_RESPONSE);
    renderPage();

    const btn = screen.getByRole("button", { name: "Terminar conexión" });
    expect(btn).toBeDisabled();
    expect(saveGithubConfig).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Repositorio/i), { target: { value: "acme/web" } });
    fireEvent.click(btn);

    await screen.findByText(/GitHub conectado/i);
    expect(saveGithubConfig).toHaveBeenCalledWith("tok", expect.objectContaining({
      org_id: "o-activa",
      repo_full_name: "acme/web",
      state: "st.mac",
      code: "c0de",
    }));
  });

  it("si GitHub no manda installation_id (solo autorizar) lo pide en el formulario", async () => {
    setQuery("?code=c0de&state=st.mac");
    vi.mocked(saveGithubConfig).mockResolvedValue(OK_RESPONSE);
    renderPage();

    fireEvent.change(screen.getByLabelText(/Installation ID/i), { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "Terminar conexión" }));

    await screen.findByText(/GitHub conectado/i);
    expect(saveGithubConfig).toHaveBeenCalledWith("tok", expect.objectContaining({
      installation_id: "42",
    }));
  });
});

describe("Callback de GitHub — errores", () => {
  it.each([
    [new ApiClientError("state caducado: vuelve a iniciar la vinculación", 403), /ha caducado/i],
    [new ApiClientError("Tu usuario de GitHub no tiene acceso a esa instalación", 403), /no tiene acceso a esa instalación/i],
    [new ApiClientError("Installation already bound", 409), /ya está vinculada a otra organización/i],
    [new ApiClientError("el state es de otra organización o de otro usuario", 403), /otra organización u otro usuario/i],
  ])("traduce el error del backend (%s) a un mensaje claro", async (error, expected) => {
    vi.mocked(saveGithubConfig).mockRejectedValue(error);
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(screen.getByRole("link", { name: "Volver a Integraciones" })).toHaveAttribute(
      "href",
      "/app/integrations",
    );
    // La vinculación pendiente se conserva para poder reintentar desde Integraciones.
    expect(readPendingGithubLink()).not.toBeNull();
  });

  it("sin code ni state no llama al backend y explica qué falta", () => {
    setQuery("?installation_id=42&setup_action=install");
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent(/no devolvió la autorización/i);
    expect(saveGithubConfig).not.toHaveBeenCalled();
  });

  it("rechaza un state distinto del iniciado en este navegador", () => {
    setQuery("?installation_id=42&code=c0de&state=otro.state");
    renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent(/no corresponde a la vinculación/i);
    expect(saveGithubConfig).not.toHaveBeenCalled();
  });

  it("setup_action=request informa de que un administrador debe aprobar", () => {
    setQuery("?setup_action=request&state=st.mac");
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent(/administrador/i);
    expect(saveGithubConfig).not.toHaveBeenCalled();
  });

  it("no vuelve a mandar el code (de un solo uso) al re-renderizar", async () => {
    vi.mocked(saveGithubConfig).mockRejectedValue(new ApiClientError("x", 400));
    const { rerender } = renderPage();
    await screen.findByRole("alert");
    await act(async () => {
      rerender(
        <QueryClientProvider client={new QueryClient()}>
          <GithubCallbackPage />
        </QueryClientProvider>,
      );
    });
    expect(saveGithubConfig).toHaveBeenCalledTimes(1);
  });
});
