// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({ setFamilyLabel: vi.fn() }));

import { setFamilyLabel } from "@/lib/api/endpoints";
import { FamilyLabelControl } from "@/components/autopilot/FamilyLabelControl";

afterEach(() => vi.clearAllMocks());

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("FamilyLabelControl", () => {
  it("etiqueta la familia con la categoría elegida", async () => {
    (setFamilyLabel as ReturnType<typeof vi.fn>).mockResolvedValue({ family_id: "fam-1", label: "flaky" });
    renderWithClient(<FamilyLabelControl familyId="fam-1" />);
    fireEvent.change(screen.getByLabelText(/categoría/i), { target: { value: "flaky" } });
    fireEvent.click(screen.getByRole("button", { name: /etiquetar familia/i }));
    await waitFor(() => expect(setFamilyLabel).toHaveBeenCalledWith("tok", "fam-1", "flaky", ""));
  });
});
