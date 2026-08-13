// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "t" }),
}));

vi.mock("@/components/providers/org-provider", () => ({
  useActiveOrg: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/lib/api/endpoints", () => ({
  listContinuityProjects: vi.fn(),
  getContinuity: vi.fn(),
  emitHandover: vi.fn(),
  getLatestHandover: vi.fn(),
}));

import { useActiveOrg } from "@/components/providers/org-provider";
import {
  getContinuity,
  getLatestHandover,
  listContinuityProjects,
} from "@/lib/api/endpoints";
import ContinuityPage from "@/app/app/continuity/page";

const INDICE_50 = {
  score: 50,
  dimensions: [
    { key: "memoria_defectos", label: "Memoria de defectos", num: 1, den: 2, ratio: 0.5, weight: 0.35 },
    { key: "razon_etiquetas", label: "El porqué de las etiquetas", num: 1, den: 2, ratio: 0.5, weight: 0.25 },
    { key: "oficio", label: "Oficio del proyecto", num: 2, den: 4, ratio: 0.5, weight: 0.25 },
    { key: "reglas_respaldadas", label: "Reglas con respaldo", num: 1, den: 2, ratio: 0.5, weight: 0.15 },
  ],
  inventario: {},
};

function setup(role: string, indice: unknown = INDICE_50) {
  (useActiveOrg as ReturnType<typeof vi.fn>).mockReturnValue({
    orgs: [{ id: "o1", name: "Org", role }],
    activeOrgId: "o1",
    isLoading: false,
    setActiveOrgId: vi.fn(),
  });
  (listContinuityProjects as ReturnType<typeof vi.fn>).mockResolvedValue({
    projects: ["checkout-suite"],
  });
  (getContinuity as ReturnType<typeof vi.fn>).mockResolvedValue(indice);
  // 404 = todavía no hay actas para este proyecto, no un error
  (getLatestHandover as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("404"));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ContinuityPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Continuidad", () => {
  it("pinta el score y las cuatro dimensiones con sus cuentas", async () => {
    setup("owner");
    expect(await screen.findByText("50")).toBeInTheDocument();
    expect(screen.getByText("Memoria de defectos")).toBeInTheDocument();
    expect(screen.getByText("Oficio del proyecto")).toBeInTheDocument();
    expect(screen.getAllByText("1 / 2").length).toBeGreaterThan(0);
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("muestra «sin datos suficientes» cuando el score es null", async () => {
    setup("owner", { ...INDICE_50, score: null });
    expect(await screen.findByText(/sin datos suficientes/i)).toBeInTheDocument();
  });

  it("una dimensión sin denominador se marca como sin datos, no como 0", async () => {
    setup("owner", {
      ...INDICE_50,
      dimensions: [
        { key: "oficio", label: "Oficio del proyecto", num: 0, den: 0, ratio: null, weight: 0.25 },
      ],
    });
    expect(await screen.findByText("sin datos")).toBeInTheDocument();
  });

  it("el botón de emitir se deshabilita sin rol owner/admin", async () => {
    setup("member");
    const btn = await screen.findByRole("button", { name: /emitir acta de traspaso/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("title", expect.stringMatching(/owner\/admin/));
  });

  it("con rol owner el botón está disponible una vez cargado el proyecto", async () => {
    setup("owner");
    // Esperar al índice: hasta que la lista de proyectos resuelve no hay proyecto
    // activo, y emitir un acta «de nada» no tendría sentido.
    await screen.findByText("50");
    expect(
      screen.getByRole("button", { name: /emitir acta de traspaso/i }),
    ).toBeEnabled();
  });
});
