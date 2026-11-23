// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/providers/auth-provider", () => ({
  useAuth: () => ({ accessToken: "tok" }),
}));
vi.mock("@/lib/api/endpoints", () => ({ getFamilyMemory: vi.fn(), getTriageVerdicts: vi.fn() }));

import { getFamilyMemory, getTriageVerdicts } from "@/lib/api/endpoints";
import { TriageMemory } from "@/components/autopilot/TriageMemory";
import { TriageVerdictList } from "@/components/autopilot/TriageVerdictList";
import type { FamilyMemory } from "@/lib/api/types";

afterEach(() => { vi.clearAllMocks(); cleanup(); });

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const MEMORY: FamilyMemory = {
  family_id: "fam1", title: "TimeoutError", label: "infra", label_text: "entorno / infraestructura",
  reason: "El sandbox del PSP se cae los lunes", reason_by: "María", reason_by_active: false,
  reason_at: "2026-10-02T08:00:00+00:00",
  lessons: [{ id: "k1", kind: "leccion", title: "Espaciar la suite", summary: "30 peticiones/min" }],
  projects: ["web", "app"], runs: 4, has_memory: true,
  related: [{ id: "k2", title: "Runbook del PSP", score: 0.8 }],
};

const mockMemory = getFamilyMemory as ReturnType<typeof vi.fn>;

describe("TriageMemory", () => {
  it("no pide la memoria hasta que se despliega", async () => {
    mockMemory.mockResolvedValue(MEMORY);
    renderWithClient(<TriageMemory familyId="fam1" />);
    expect(mockMemory).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Memoria del equipo" }));
    expect(await screen.findByText(/El sandbox del PSP se cae los lunes/)).toBeInTheDocument();
    expect(mockMemory).toHaveBeenCalledWith("tok", "fam1");
  });

  it("muestra etiqueta, razón con autor ausente, lección, relacionados y enlace a la familia", async () => {
    mockMemory.mockResolvedValue(MEMORY);
    renderWithClient(<TriageMemory familyId="fam1" />);
    fireEvent.click(screen.getByRole("button", { name: "Memoria del equipo" }));
    expect(await screen.findByText("Etiqueta del equipo: entorno / infraestructura")).toBeInTheDocument();
    expect(screen.getByText(/María \(ya no está en la organización\), 2026-10-02/)).toBeInTheDocument();
    expect(screen.getByText("Espaciar la suite")).toBeInTheDocument();
    expect(screen.getByText("Runbook del PSP")).toBeInTheDocument();
    expect(screen.getByText(/Vista en 4 runs · proyectos: web, app/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Abrir la familia/ })).toHaveAttribute(
      "href", "/app/defects?family=fam1");
  });

  it("sin memoria invita a dejarla escrita", async () => {
    mockMemory.mockResolvedValue({ ...MEMORY, label: "unknown", label_text: null, reason: null,
                                   lessons: [], related: [], has_memory: false });
    renderWithClient(<TriageMemory familyId="fam1" />);
    fireEvent.click(screen.getByRole("button", { name: "Memoria del equipo" }));
    expect(await screen.findByText(/aún no ha dejado nada escrito/)).toBeInTheDocument();
  });

  it("si falla la carga lo dice sin romper la lista", async () => {
    mockMemory.mockRejectedValue(new Error("502"));
    renderWithClient(<TriageMemory familyId="fam1" />);
    fireEvent.click(screen.getByRole("button", { name: "Memoria del equipo" }));
    expect(await screen.findByText(/No se pudo cargar la memoria/)).toBeInTheDocument();
  });
});

describe("TriageVerdictList + memoria", () => {
  it("ofrece la memoria solo en los veredictos con familia", async () => {
    (getTriageVerdicts as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "v1", failure_id: "f1", category: "real", confidence: 0.9, rule_applied: "R4_real_recurrent",
        requires_approval: false, llm_assisted: false, status: "resolved",
        evidence_bundle: { family_id: "fam1" } },
      { id: "v2", failure_id: "f2", category: "flaky", confidence: 0.9, rule_applied: "R1_flaky",
        requires_approval: false, llm_assisted: false, status: "resolved", evidence_bundle: {} },
    ]);
    renderWithClient(<TriageVerdictList runId="r1" />);
    expect(await screen.findAllByRole("button", { name: "Memoria del equipo" })).toHaveLength(1);
  });
});
