// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/endpoints", () => ({
  getGithubInstallUrl: vi.fn(),
}));

vi.mock("@/lib/github/link", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/github/link")>();
  return { ...actual, redirectTo: vi.fn() };
});

import { getGithubInstallUrl } from "@/lib/api/endpoints";
import { ApiClientError } from "@/lib/api/client";
import { readPendingGithubLink, redirectTo } from "@/lib/github/link";
import { GithubConnectButton } from "@/components/integrations/GithubConnectButton";

const INSTALL = {
  state: "st.mac",
  install_url: "https://github.com/apps/mnemo/installations/new?state=st.mac",
  authorize_url: "https://github.com/login/oauth/authorize?client_id=x&state=st.mac",
};

beforeEach(() => window.sessionStorage.clear());
afterEach(cleanup);

function typeRepo(value: string) {
  fireEvent.change(screen.getByLabelText(/Repositorio/i), { target: { value } });
}

describe("GithubConnectButton", () => {
  it("deshabilita el botón hasta que el repositorio tiene formato owner/repo", () => {
    render(<GithubConnectButton accessToken="tok" orgId="o1" />);
    const btn = screen.getByRole("button", { name: "Conectar con GitHub" });
    expect(btn).toBeDisabled();
    typeRepo("sin-barra");
    expect(btn).toBeDisabled();
    typeRepo("acme/web");
    expect(btn).not.toBeDisabled();
  });

  it("pide install-url, guarda la vinculación pendiente y redirige a GitHub", async () => {
    vi.mocked(getGithubInstallUrl).mockResolvedValue(INSTALL);
    render(<GithubConnectButton accessToken="tok" orgId="o1" />);
    typeRepo(" acme/web ");
    fireEvent.click(screen.getByRole("button", { name: "Conectar con GitHub" }));

    await waitFor(() => expect(redirectTo).toHaveBeenCalledWith(INSTALL.install_url));
    expect(getGithubInstallUrl).toHaveBeenCalledWith("tok", { org_id: "o1" });
    expect(readPendingGithubLink()).toEqual({
      orgId: "o1",
      repoFullName: "acme/web",
      state: "st.mac",
    });
  });

  it("«Solo autorizar» redirige a la URL de autorización OAuth", async () => {
    vi.mocked(getGithubInstallUrl).mockResolvedValue(INSTALL);
    render(<GithubConnectButton accessToken="tok" orgId="o1" initialRepo="acme/web" />);
    fireEvent.click(screen.getByRole("button", { name: /Solo autorizar/i }));
    await waitFor(() => expect(redirectTo).toHaveBeenCalledWith(INSTALL.authorize_url));
  });

  it("muestra un error claro si la GitHub App no está configurada (503) y no redirige", async () => {
    vi.mocked(getGithubInstallUrl).mockRejectedValue(
      new ApiClientError("El servidor no ha podido completar la acción (error 503).", 503),
    );
    render(<GithubConnectButton accessToken="tok" orgId="o1" initialRepo="acme/web" />);
    fireEvent.click(screen.getByRole("button", { name: "Conectar con GitHub" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no está configurada en el servidor/i);
    expect(redirectTo).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Conectar con GitHub" })).not.toBeDisabled();
  });
});
