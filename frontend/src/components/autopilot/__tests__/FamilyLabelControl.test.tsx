// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({ useAuth: () => ({ accessToken: "tok" }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/endpoints", () => ({ setFamilyLabel: vi.fn() }));

import { setFamilyLabel } from "@/lib/api/endpoints";
import { FamilyLabelControl } from "@/components/autopilot/FamilyLabelControl";

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

afterEach(() => { vi.clearAllMocks(); cleanup(); });

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("FamilyLabelControl", () => {
  it("etiqueta la familia con la categoría elegida (Select unificado)", async () => {
    const user = userEvent.setup();
    (setFamilyLabel as ReturnType<typeof vi.fn>).mockResolvedValue({ family_id: "fam-1", label: "flaky" });
    const { container } = renderWithClient(<FamilyLabelControl familyId="fam-1" />);

    // Open the Select dropdown
    await user.click(within(container).getByRole("combobox", { name: /categoría/i }));

    // Click the "flaky" option
    const flakyOption = await screen.findByRole("option", { name: "flaky" });
    await user.click(flakyOption);

    // Submit
    await user.click(screen.getByRole("button", { name: /etiquetar familia/i }));
    await waitFor(() => expect(setFamilyLabel).toHaveBeenCalledWith("tok", "fam-1", "flaky", ""));
  });

  it("cambia el valor del Select y lo pasa correctamente al guardar", async () => {
    const user = userEvent.setup();
    (setFamilyLabel as ReturnType<typeof vi.fn>).mockResolvedValue({ family_id: "fam-2", label: "real" });
    const { container } = renderWithClient(<FamilyLabelControl familyId="fam-2" />);

    // Change to "real"
    await user.click(within(container).getByRole("combobox", { name: /categoría/i }));
    await user.click(await screen.findByRole("option", { name: "real" }));

    await user.click(screen.getByRole("button", { name: /etiquetar familia/i }));
    await waitFor(() => expect(setFamilyLabel).toHaveBeenCalledWith("tok", "fam-2", "real", ""));
  });
});
