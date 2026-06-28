// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "t" }),
}));

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: vi.fn(),
}));

vi.mock("@/lib/api/endpoints", () => ({
  getGithubConfig: vi.fn(),
  listRepoTests: vi.fn(),
  listKnowledge: vi.fn(),
  getGaps: vi.fn(),
}));

import { useActiveOrg } from "@/components/providers/org-provider";
import {
  getGithubConfig,
  listRepoTests,
  listKnowledge,
  getGaps,
} from "@/lib/api/endpoints";
import DashboardPage from "@/app/app/page";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("steps 1 y 2 done cuando github configurado y tests indexados", async () => {
    (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({
      activeOrgId: "o1",
      isLoading: false,
    });
    (getGithubConfig as ReturnType<typeof vi.fn>).mockResolvedValue({
      configured: true,
    });
    (listRepoTests as ReturnType<typeof vi.fn>).mockResolvedValue([
      { path: "a" },
    ]);
    (listKnowledge as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (getGaps as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    renderWithClient(<DashboardPage />);

    await waitFor(() => {
      expect(screen.getByTestId("step-done-1")).toBeDefined();
      expect(screen.getByTestId("step-done-2")).toBeDefined();
      expect(screen.getByTestId("step-todo-5")).toBeDefined();
    });

    expect(screen.getByTestId("step-todo-3")).toBeDefined();
    expect(screen.getByTestId("step-todo-4")).toBeDefined();
  });

  it("muestra empty-state con enlace /app/org cuando no hay orgId", async () => {
    (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({
      activeOrgId: "",
      isLoading: false,
    });

    renderWithClient(<DashboardPage />);

    await waitFor(() => {
      const link = screen.getByRole("link", { name: /organización/i });
      expect(link.getAttribute("href")).toBe("/app/org");
    });
  });
});
