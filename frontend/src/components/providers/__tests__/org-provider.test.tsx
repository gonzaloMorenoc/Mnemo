// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({ getOrganizations: vi.fn() }));

import { getOrganizations } from "@/lib/api/endpoints";
import { OrgProvider, useActiveOrg } from "@/components/providers/org-provider";
import { OrgSwitcher } from "@/components/layout/org-switcher";

afterEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  cleanup();
});

const ORG_A = { id: "org-a", name: "Org A", join_code: "aaa", role: null, created_at: null };
const ORG_B = { id: "org-b", name: "Org B", join_code: "bbb", role: null, created_at: null };

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

function OrgIdDisplay() {
  const { activeOrgId } = useActiveOrg();
  return <span data-testid="active-org">{activeOrgId}</span>;
}

function OrgIdSetter() {
  const { activeOrgId, setActiveOrgId } = useActiveOrg();
  return (
    <>
      <span data-testid="active-org">{activeOrgId}</span>
      <button onClick={() => setActiveOrgId(ORG_B.id)}>Switch to B</button>
    </>
  );
}

describe("OrgProvider", () => {
  it("defaults to the first org once loaded", async () => {
    (getOrganizations as ReturnType<typeof vi.fn>).mockResolvedValue([ORG_A, ORG_B]);
    renderWithClient(
      <OrgProvider>
        <OrgIdDisplay />
      </OrgProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_A.id));
  });

  it("setActiveOrgId updates state and persists to localStorage", async () => {
    (getOrganizations as ReturnType<typeof vi.fn>).mockResolvedValue([ORG_A, ORG_B]);
    renderWithClient(
      <OrgProvider>
        <OrgIdSetter />
      </OrgProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_A.id));
    fireEvent.click(screen.getByRole("button", { name: /switch to b/i }));
    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_B.id));
    expect(localStorage.getItem("mnemo.activeOrgId")).toBe(ORG_B.id);
  });

  it("restores a valid persisted org from localStorage", async () => {
    localStorage.setItem("mnemo.activeOrgId", ORG_B.id);
    (getOrganizations as ReturnType<typeof vi.fn>).mockResolvedValue([ORG_A, ORG_B]);
    renderWithClient(
      <OrgProvider>
        <OrgIdDisplay />
      </OrgProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_B.id));
  });
});

describe("OrgSwitcher", () => {
  it("renders a select with both orgs and switching updates the active org", async () => {
    (getOrganizations as ReturnType<typeof vi.fn>).mockResolvedValue([ORG_A, ORG_B]);
    renderWithClient(
      <OrgProvider>
        <OrgSwitcher />
        <OrgIdDisplay />
      </OrgProvider>,
    );
    const select = await screen.findByRole("combobox", { name: /organización/i });
    expect(select).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Org A" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Org B" })).toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_A.id));
    fireEvent.change(select, { target: { value: ORG_B.id } });
    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_B.id));
  });

  it("renders single org name as plain text (no select)", async () => {
    (getOrganizations as ReturnType<typeof vi.fn>).mockResolvedValue([ORG_A]);
    renderWithClient(
      <OrgProvider>
        <OrgSwitcher />
      </OrgProvider>,
    );
    await waitFor(() => expect(screen.getByText("Org A")).toBeInTheDocument());
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
