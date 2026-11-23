// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok", user: { id: "me" } }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api/members", () => ({
  listMembers: vi.fn(),
  changeMemberRole: vi.fn(),
  removeMember: vi.fn(),
  rotateJoinCode: vi.fn(),
}));

import { OrgMembersPanel } from "@/components/org/OrgMembersPanel";
import { changeMemberRole, listMembers, removeMember, rotateJoinCode } from "@/lib/api/members";
import type { OrganizationResponse } from "@/lib/api/types";

const ADMIN_ORG: OrganizationResponse = {
  id: "o1",
  name: "Acme",
  join_code: "abc123def0",
  join_code_expires_at: "2026-12-01T00:00:00+00:00",
  role: "admin",
  created_at: null,
};

const MEMBERS = [
  { user_id: "me", role: "admin", email: "yo@acme.com", display_name: null, created_at: null },
  { user_id: "u2", role: "viewer", email: "ana@acme.com", display_name: "Ana", created_at: null },
];

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

function renderPanel(org: OrganizationResponse) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrgMembersPanel org={org} />
    </QueryClientProvider>,
  );
}

describe("OrgMembersPanel", () => {
  it("lista los miembros con su rol para un admin", async () => {
    vi.mocked(listMembers).mockResolvedValue(MEMBERS);
    renderPanel(ADMIN_ORG);
    expect(await screen.findByText("Ana")).toBeTruthy();
    expect(screen.getByText("ana@acme.com")).toBeTruthy();
    expect(listMembers).toHaveBeenCalledWith("tok", "o1");
  });

  it("muestra el código de unión y lo rota", async () => {
    vi.mocked(listMembers).mockResolvedValue(MEMBERS);
    vi.mocked(rotateJoinCode).mockResolvedValue({
      join_code: "ffff00001111",
      join_code_expires_at: "2026-12-08T00:00:00+00:00",
    });
    renderPanel(ADMIN_ORG);
    expect(await screen.findByText("abc123def0")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /rotar/i }));
    await waitFor(() => expect(rotateJoinCode).toHaveBeenCalledWith("tok", "o1"));
    expect(await screen.findByText("ffff00001111")).toBeTruthy();
  });

  it("cambia el rol con el selector", async () => {
    vi.mocked(listMembers).mockResolvedValue(MEMBERS);
    vi.mocked(changeMemberRole).mockResolvedValue({ user_id: "u2", role: "member" });
    renderPanel(ADMIN_ORG);
    const select = await screen.findByLabelText(/rol de ana/i);
    fireEvent.change(select, { target: { value: "member" } });
    await waitFor(() => expect(changeMemberRole).toHaveBeenCalledWith("tok", "o1", "u2", "member"));
  });

  it("pide confirmación en la propia UI antes de expulsar", async () => {
    vi.mocked(listMembers).mockResolvedValue(MEMBERS);
    vi.mocked(removeMember).mockResolvedValue({ removed: true });
    const confirmSpy = vi.spyOn(window, "confirm");
    renderPanel(ADMIN_ORG);
    const row = (await screen.findByText("Ana")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /expulsar/i }));
    expect(removeMember).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByRole("button", { name: /sí, expulsar/i }));
    await waitFor(() => expect(removeMember).toHaveBeenCalledWith("tok", "o1", "u2"));
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("cancelar la confirmación no expulsa a nadie", async () => {
    vi.mocked(listMembers).mockResolvedValue(MEMBERS);
    renderPanel(ADMIN_ORG);
    const row = (await screen.findByText("Ana")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /expulsar/i }));
    fireEvent.click(within(row).getByRole("button", { name: /cancelar/i }));
    expect(removeMember).not.toHaveBeenCalled();
    expect(within(row).getByRole("button", { name: /expulsar/i })).toBeTruthy();
  });

  it("un admin no puede tocar a un owner ni ascender a owner", async () => {
    vi.mocked(listMembers).mockResolvedValue([
      { user_id: "boss", role: "owner", email: "jefa@acme.com", display_name: "Jefa", created_at: null },
      ...MEMBERS,
    ]);
    renderPanel(ADMIN_ORG);
    const ownerRow = (await screen.findByText("Jefa")).closest("li") as HTMLElement;
    expect(within(ownerRow).queryByRole("combobox")).toBeNull();
    expect(within(ownerRow).queryByRole("button", { name: /expulsar/i })).toBeNull();
    const select = screen.getByLabelText(/rol de ana/i) as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).not.toContain("owner");
  });

  it("no ofrece subirse de rol a uno mismo", async () => {
    vi.mocked(listMembers).mockResolvedValue(MEMBERS);
    renderPanel(ADMIN_ORG);
    const meRow = (await screen.findByText("yo@acme.com")).closest("li") as HTMLElement;
    const select = within(meRow).getByRole("combobox") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.value);
    expect(options).toEqual(["admin", "member", "viewer"]);
  });

  it("para quien no es admin no pide miembros ni enseña el código", () => {
    renderPanel({ ...ADMIN_ORG, role: "viewer", join_code: null, join_code_expires_at: null });
    expect(listMembers).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /rotar/i })).toBeNull();
    expect(screen.getByText(/solo lectura/i)).toBeTruthy();
  });
});
