// @vitest-environment jsdom
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: vi.fn(),
}));

import { useActiveOrg } from "@/components/providers/org-provider";
import { OrgSwitcher } from "@/components/layout/org-switcher";

afterEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe("OrgSwitcher", () => {
  it("con una sola org, el nombre es un enlace a /app/org (no texto muerto)", () => {
    vi.mocked(useActiveOrg).mockReturnValue({
      orgs: [{ id: "o1", name: "Demo MTP" }],
      activeOrgId: "o1",
      setActiveOrgId: vi.fn(),
    } as unknown as ReturnType<typeof useActiveOrg>);
    render(<OrgSwitcher />);
    expect(screen.getByRole("link", { name: /Demo MTP/ })).toHaveAttribute("href", "/app/org");
  });

  it("con varias orgs renderiza el selector", () => {
    vi.mocked(useActiveOrg).mockReturnValue({
      orgs: [
        { id: "o1", name: "Demo MTP" },
        { id: "o2", name: "Cliente Beta" },
      ],
      activeOrgId: "o1",
      setActiveOrgId: vi.fn(),
    } as unknown as ReturnType<typeof useActiveOrg>);
    render(<OrgSwitcher />);
    expect(screen.getByRole("combobox", { name: "Organización" })).toBeInTheDocument();
  });
});
