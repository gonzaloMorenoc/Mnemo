// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));
vi.mock("@/lib/api/endpoints", () => ({
  listContinuityProjects: vi.fn(),
  getContinuity: vi.fn(),
}));

import { getContinuity, listContinuityProjects } from "@/lib/api/endpoints";
import { RotationRiskMap } from "@/components/continuity/RotationRiskMap";

const SCORES: Record<string, number | null> = {
  "checkout-suite": 95, "banca-movil": 25, "api-pagos": 54, "nuevo": null,
};

function setup(props: Partial<React.ComponentProps<typeof RotationRiskMap>> = {}) {
  (listContinuityProjects as ReturnType<typeof vi.fn>).mockResolvedValue({ projects: Object.keys(SCORES) });
  (getContinuity as ReturnType<typeof vi.fn>).mockImplementation(
    (_t: string, _o: string, p: string) => Promise.resolve({ score: SCORES[p], dimensions: [], inventario: {} }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RotationRiskMap accessToken="t" orgId="o1" {...props} />
    </QueryClientProvider>,
  );
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("RotationRiskMap", () => {
  it("ordena los proyectos del más expuesto al más cubierto, con los sin datos al final", async () => {
    setup();
    await screen.findByText("95");
    const filas = screen.getAllByRole("button").map((b) => within(b).getByTestId("proyecto").textContent);
    expect(filas).toEqual(["banca-movil", "api-pagos", "checkout-suite", "nuevo"]);
  });

  it("cada proyecto dice su banda de riesgo en texto, no solo en color", async () => {
    setup();
    const banca = (await screen.findByText("banca-movil")).closest("button")!;
    expect(within(banca).getByText("Riesgo alto")).toBeInTheDocument();
    const checkout = screen.getByText("checkout-suite").closest("button")!;
    expect(within(checkout).getByText("Cubierto")).toBeInTheDocument();
  });

  it("marca el proyecto activo y avisa al elegir otro", async () => {
    const onSelect = vi.fn();
    setup({ activeProject: "checkout-suite", onSelect });
    const checkout = (await screen.findByText("checkout-suite")).closest("button")!;
    expect(checkout).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByText("banca-movil").closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("banca-movil");
  });

  it("en el resumen del Dashboard: solo los N más expuestos, como enlaces a su detalle", async () => {
    setup({ limit: 2, hrefFor: (p) => `/app/continuity?project=${p}` });
    await screen.findByText("banca-movil");
    const enlaces = screen.getAllByRole("link");
    expect(enlaces.map((a) => a.getAttribute("href"))).toEqual([
      "/app/continuity?project=banca-movil",
      "/app/continuity?project=api-pagos",
    ]);
    expect(screen.queryByText("checkout-suite")).toBeNull();
  });
});
