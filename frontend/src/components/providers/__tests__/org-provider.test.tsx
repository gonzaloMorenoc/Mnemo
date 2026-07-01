// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("@/lib/api/endpoints", () => ({ getOrganizations: vi.fn() }));

import { getOrganizations } from "@/lib/api/endpoints";
import { OrgProvider, useActiveOrg } from "@/components/providers/org-provider";
import { OrgSwitcher } from "@/components/layout/org-switcher";

// Radix UI pointer/scroll APIs not available in jsdom
beforeEach(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => undefined;
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => undefined;
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
});

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
  const { activeOrgId, isLoading } = useActiveOrg();
  return (
    <>
      <span data-testid="active-org">{activeOrgId}</span>
      <span data-testid="is-loading">{String(isLoading)}</span>
    </>
  );
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

  // Optimistic: stored id is shown BEFORE the query resolves
  it("O1 — muestra el id guardado en localStorage antes de que /v2/orgs resuelva", async () => {
    localStorage.setItem("mnemo.activeOrgId", "org-guardada");
    let resolveOrgs!: (value: typeof ORG_A[]) => void;
    const slowPromise = new Promise<typeof ORG_A[]>((res) => { resolveOrgs = res; });
    (getOrganizations as ReturnType<typeof vi.fn>).mockReturnValue(slowPromise);

    renderWithClient(
      <OrgProvider>
        <OrgIdDisplay />
      </OrgProvider>,
    );

    // Before the query resolves, the stored id must already be visible
    await waitFor(() =>
      expect(screen.getByTestId("active-org").textContent).toBe("org-guardada"),
    );

    // After resolving with a list that does NOT contain the stored id, correct to orgs[0]
    resolveOrgs([ORG_A]); // ORG_A.id = "org-a", not "org-guardada"
    await waitFor(() =>
      expect(screen.getByTestId("active-org").textContent).toBe(ORG_A.id),
    );
  });

  // I2: isLoading is exposed and transitions false→true→false as query resolves
  it("I2 — isLoading es true mientras la query está pendiente y false cuando resuelve", async () => {
    let resolveOrgs!: (value: typeof ORG_A[]) => void;
    const slowPromise = new Promise<typeof ORG_A[]>((res) => { resolveOrgs = res; });
    (getOrganizations as ReturnType<typeof vi.fn>).mockReturnValue(slowPromise);

    renderWithClient(
      <OrgProvider>
        <OrgIdDisplay />
      </OrgProvider>,
    );

    // Initially isLoading should be true while the query is in-flight
    await waitFor(() => expect(screen.getByTestId("is-loading").textContent).toBe("true"));

    // Resolve and isLoading should become false
    resolveOrgs([ORG_A]);
    await waitFor(() => expect(screen.getByTestId("is-loading").textContent).toBe("false"));
    expect(screen.getByTestId("active-org").textContent).toBe(ORG_A.id);
  });
});

describe("OrgSwitcher", () => {
  it("renders a select trigger with the active org and switching updates the active org", async () => {
    const user = userEvent.setup();
    (getOrganizations as ReturnType<typeof vi.fn>).mockResolvedValue([ORG_A, ORG_B]);
    const { container } = renderWithClient(
      <OrgProvider>
        <OrgSwitcher />
        <OrgIdDisplay />
      </OrgProvider>,
    );
    // Radix Select renders a combobox trigger
    const trigger = await screen.findByRole("combobox", { name: /organización/i });
    expect(trigger).toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId("active-org").textContent).toBe(ORG_A.id));

    // Open dropdown
    await user.click(within(container).getByRole("combobox", { name: /organización/i }));

    // Select Org B option
    const orgBOption = await screen.findByRole("option", { name: "Org B" });
    await user.click(orgBOption);

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
