// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({
  listIngestTokens: vi.fn(),
  createIngestToken: vi.fn(),
  revokeIngestToken: vi.fn(),
}));

import { IngestTokensPanel } from "@/components/integrations/IngestTokensPanel";
import * as endpoints from "@/lib/api/endpoints";

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IngestTokensPanel orgId="o1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("IngestTokensPanel", () => {
  it("lista los tokens con su estado", async () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([
      { id: "t1", name: "GitHub Actions", created_at: "2026-07-22T10:00:00", last_used_at: null, revoked_at: null },
      { id: "t2", name: "Jenkins viejo", created_at: "2026-07-01T10:00:00", last_used_at: "2026-07-10T10:00:00", revoked_at: "2026-07-20T10:00:00" },
    ]);
    renderPanel();
    await waitFor(() => expect(screen.getByText("GitHub Actions")).toBeInTheDocument());
    expect(screen.getByText("Activo")).toBeInTheDocument();
    expect(screen.getByText("Revocado")).toBeInTheDocument();
  });

  it("crear muestra el token EN CLARO una vez + el curl listo", async () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([]);
    vi.mocked(endpoints.createIngestToken).mockResolvedValue({
      id: "t9", name: "CI web", created_at: "2026-07-22", last_used_at: null,
      revoked_at: null, token: "mnemo_it_secreto123",
    });
    renderPanel();
    fireEvent.change(screen.getByLabelText(/Nombre del token/i), { target: { value: "CI web" } });
    fireEvent.click(screen.getByRole("button", { name: /Crear token/i }));
    await waitFor(() =>
      expect(screen.getByText("mnemo_it_secreto123")).toBeInTheDocument());
    expect(screen.getByText(/no volverá a mostrarse/i)).toBeInTheDocument();
    expect(endpoints.createIngestToken).toHaveBeenCalledWith("tok", "o1", "CI web");
    // El curl referencia la variable de entorno, NUNCA el secreto literal
    const curl = screen.getByText(/\/v2\/ci\/ingest/);
    expect(curl.textContent).toContain("$MNEMO_INGEST_TOKEN");
    expect(curl.textContent).not.toContain("mnemo_it_secreto123");
    expect(screen.getByText(/Guárdalo como secreto/i)).toBeInTheDocument();
  });

  it("el claro NO se muestra si cambia la organización activa", async () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([]);
    vi.mocked(endpoints.createIngestToken).mockResolvedValue({
      id: "t9", name: "CI web", created_at: "2026-07-22", last_used_at: null,
      revoked_at: null, token: "mnemo_it_secreto123",
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <IngestTokensPanel orgId="o1" />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText(/Nombre del token/i), { target: { value: "CI web" } });
    fireEvent.click(screen.getByRole("button", { name: /Crear token/i }));
    await waitFor(() =>
      expect(screen.getByText("mnemo_it_secreto123")).toBeInTheDocument());
    rerender(
      <QueryClientProvider client={client}>
        <IngestTokensPanel orgId="o2" />
      </QueryClientProvider>,
    );
    expect(screen.queryByText("mnemo_it_secreto123")).toBeNull();
  });

  it("si la lista falla, muestra el error (no parece 'sin tokens')", async () => {
    vi.mocked(endpoints.listIngestTokens).mockRejectedValue(new Error("Backend caído"));
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText(/No se pudieron cargar los tokens/i)).toBeInTheDocument());
  });

  it("no se puede crear sin organización activa", () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <IngestTokensPanel orgId="" />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText(/Nombre del token/i), { target: { value: "CI web" } });
    expect(screen.getByRole("button", { name: /Crear token/i })).toBeDisabled();
  });

  it("revocar pide confirmación y llama al endpoint", async () => {
    vi.mocked(endpoints.listIngestTokens).mockResolvedValue([
      { id: "t1", name: "GitHub Actions", created_at: null, last_used_at: null, revoked_at: null },
    ]);
    vi.mocked(endpoints.revokeIngestToken).mockResolvedValue({ revoked: true });
    renderPanel();
    await screen.findByText("GitHub Actions");
    fireEvent.click(screen.getByRole("button", { name: /^Revocar$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^Revocar$/i, hidden: false }));
    await waitFor(() =>
      expect(endpoints.revokeIngestToken).toHaveBeenCalledWith("tok", "t1"));
  });
});
