// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));

const mockActiveOrg: { value: string | null; isLoading: boolean } = { value: "o1", isLoading: false };

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: () => ({
    activeOrgId: mockActiveOrg.value,
    isLoading: mockActiveOrg.isLoading,
    orgs: mockActiveOrg.value
      ? [{ id: "o1", name: "Test Org", join_code: "ABC", role: "owner", created_at: null }]
      : [],
    setActiveOrgId: vi.fn(),
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api/endpoints", () => ({
  getOrganizations: vi.fn().mockResolvedValue([{ id: "o1", name: "Test Org" }]),
  getJiraConfig: vi.fn().mockResolvedValue({ configured: false, base_url: null, email: null, jql: null }),
  saveJiraConfig: vi.fn(),
  pullJiraBugs: vi.fn(),
  ingestJiraFile: vi.fn(),
  getGithubConfig: vi.fn(),
  saveGithubConfig: vi.fn(),
  indexRepo: vi.fn(),
  listRepoTests: vi.fn(),
}));

import {
  getGithubConfig,
  indexRepo,
  listRepoTests,
} from "@/lib/api/endpoints";
import { ApiClientError } from "@/lib/api/client";
import { toast } from "sonner";
import IntegrationsPage from "@/app/app/integrations/page";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
  mockActiveOrg.value = "o1";
  mockActiveOrg.isLoading = false;
});

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const MOCK_INDEX_RESULT = {
  indexed: 42,
  by_domain: { auth: 10, payments: 32 },
  skipped: 3,
};

const MOCK_REPO_TESTS = [
  { path: "tests/auth/login.spec.ts", framework: "playwright", domain: "auth" },
  { path: "tests/payments/checkout.spec.ts", framework: "playwright", domain: "payments" },
];

describe("IntegrationsPage — GitHub config configurado", () => {
  it("con GitHub configurado, 'Indexar tests del repo' no está deshabilitado y al hacer click llama a indexRepo con org_id", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
      repo_full_name: "org/repo",
      installation_id: "123",
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (indexRepo as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_INDEX_RESULT);

    renderWithClient(<IntegrationsPage />);

    // Wait for the button to be enabled (query resolves → githubConfigured=true)
    const btn = await waitFor(() => {
      const b = screen.getByRole("button", { name: /Indexar tests del repo/i });
      expect(b).not.toBeDisabled();
      return b;
    });

    fireEvent.click(btn);

    await waitFor(() => {
      expect(indexRepo).toHaveBeenCalledWith("tok", { org_id: "o1" });
    });
  });

  it("al indexar con éxito muestra toast.success con el nº de tests indexados", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
      repo_full_name: "org/repo",
      installation_id: "123",
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (indexRepo as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_INDEX_RESULT);

    renderWithClient(<IntegrationsPage />);

    // Wait for query to settle and button to be enabled
    const btn = await waitFor(() => {
      const b = screen.getByRole("button", { name: /Indexar tests del repo/i });
      expect(b).not.toBeDisabled();
      return b;
    });

    fireEvent.click(btn);

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("42 tests indexados");
    });
  });
});

describe("IntegrationsPage — listRepoTests renderiza tests", () => {
  it("renderiza un test con path · framework · domain cuando listRepoTests devuelve datos", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
      repo_full_name: "org/repo",
      installation_id: "123",
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_REPO_TESTS);
    (indexRepo as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_INDEX_RESULT);

    renderWithClient(<IntegrationsPage />);

    expect(await screen.findByText("tests/auth/login.spec.ts")).toBeInTheDocument();
    expect(screen.getByText("tests/payments/checkout.spec.ts")).toBeInTheDocument();
  });

  it("muestra el resumen de counts por dominio", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
      repo_full_name: "org/repo",
      installation_id: "123",
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_REPO_TESTS);
    (indexRepo as ReturnType<typeof vi.fn>).mockResolvedValue(MOCK_INDEX_RESULT);

    renderWithClient(<IntegrationsPage />);

    expect(await screen.findByText("auth: 1")).toBeInTheDocument();
    expect(screen.getByText("payments: 1")).toBeInTheDocument();
  });
});

describe("IntegrationsPage — GitHub NO configurado", () => {
  it("el botón 'Indexar tests del repo' está deshabilitado cuando GitHub no está configurado", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: false,
      repo_full_name: null,
      installation_id: null,
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderWithClient(<IntegrationsPage />);

    const btn = await screen.findByRole("button", { name: /Indexar tests del repo/i });
    expect(btn).toBeDisabled();
  });

  it("muestra el hint 'configura GitHub primero' cuando GitHub no está configurado", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: false,
      repo_full_name: null,
      installation_id: null,
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderWithClient(<IntegrationsPage />);

    expect(await screen.findByText(/configura GitHub primero/i)).toBeInTheDocument();
  });
});

describe("IntegrationsPage — error al indexar", () => {
  it("muestra toast.error con el mensaje cuando indexRepo rechaza", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
      repo_full_name: "org/repo",
      installation_id: "123",
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (indexRepo as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("conexión fallida"));

    renderWithClient(<IntegrationsPage />);

    const btn = await waitFor(() => {
      const b = screen.getByRole("button", { name: /Indexar tests del repo/i });
      expect(b).not.toBeDisabled();
      return b;
    });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("conexión fallida");
    });
  });

  it("muestra 'Configura GitHub' cuando indexRepo rechaza con ApiClientError 503", async () => {
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
      repo_full_name: "org/repo",
      installation_id: "123",
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (indexRepo as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiClientError("GitHub integration not configured", 503),
    );

    renderWithClient(<IntegrationsPage />);

    const btn = await waitFor(() => {
      const b = screen.getByRole("button", { name: /Indexar tests del repo/i });
      expect(b).not.toBeDisabled();
      return b;
    });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Configura GitHub");
    });
  });
});
