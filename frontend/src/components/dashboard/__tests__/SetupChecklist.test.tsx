// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SetupChecklist, type SetupStep } from "@/components/dashboard/SetupChecklist";

const STEPS: SetupStep[] = [
  {
    n: 1,
    title: "Conecta GitHub",
    description: "d",
    href: "/app/integrations",
    cta: "Configurar",
    done: true,
  },
  {
    n: 2,
    title: "Indexa los tests",
    description: "desc",
    href: "/app/integrations",
    cta: "Indexar",
    done: false,
  },
];

describe("SetupChecklist", () => {
  it("muestra el check para pasos completados y el círculo para los pendientes", () => {
    render(<SetupChecklist steps={STEPS} />);
    expect(screen.getByTestId("step-done-1")).toBeDefined();
    expect(screen.getByTestId("step-todo-2")).toBeDefined();
  });

  it("cada CTA es un enlace al href del paso", () => {
    render(<SetupChecklist steps={STEPS} />);
    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/app/integrations");
  });

  it("muestra el skeleton cuando loading=true", () => {
    render(<SetupChecklist steps={[]} loading={true} />);
    expect(screen.getByTestId("checklist-skeleton")).toBeDefined();
  });

  it("el paso highlight usa variante default en el botón", () => {
    const highlightStep: SetupStep = {
      n: 5,
      title: "Genera",
      description: "d",
      href: "/app/graph",
      cta: "Generar",
      done: false,
      highlight: true,
    };
    render(<SetupChecklist steps={[highlightStep]} />);
    expect(screen.getByTestId("step-todo-5")).toBeDefined();
    // The CTA link should exist and point to the correct href
    const link = screen.getByRole("link", { name: "Generar" });
    expect(link.getAttribute("href")).toBe("/app/graph");
  });
});
