import { describe, expect, it, vi } from "vitest";

// El layout raíz carga fuentes de Google en build; aquí basta con su metadata.
vi.mock("next/font/google", () => ({
  Manrope: () => ({ variable: "" }),
  JetBrains_Mono: () => ({ variable: "" }),
}));
vi.mock("@/components/providers/app-providers", () => ({ AppProviders: () => null }));
vi.mock("@/components/layout/auth-guard", () => ({ AuthGuard: () => null }));
vi.mock("@/components/layout/app-shell", () => ({ AppShell: () => null }));

const SECTIONS: ReadonlyArray<readonly [string, () => Promise<{ metadata: { title?: unknown } }>]> = [
  ["Iniciar sesión", () => import("@/app/login/layout")],
  ["Crear cuenta", () => import("@/app/signup/layout")],
  ["Verificar un acta", () => import("@/app/verify/layout")],
  ["Panel de control", () => import("@/app/app/layout")],
  ["Continuidad", () => import("@/app/app/continuity/layout")],
  ["Conocimiento", () => import("@/app/app/knowledge/layout")],
  ["Plan de pruebas", () => import("@/app/app/test-plan/layout")],
];

describe("<title> por página (F7/F16)", () => {
  it("la plantilla raíz añade la marca a cada título", async () => {
    const { metadata } = await import("@/app/layout");
    expect(metadata.title).toEqual(expect.objectContaining({ template: "%s · Mnemo" }));
  });

  it.each(SECTIONS)("%s tiene su propio título", async (title, load) => {
    const { metadata } = await load();
    expect(metadata.title).toBe(title);
  });
});
