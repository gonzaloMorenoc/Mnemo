import { describe, expect, it } from "vitest";

import { DEFAULT_AFTER_LOGIN, safeNextPath } from "@/lib/safe-redirect";

describe("safeNextPath: solo redirige a rutas internas", () => {
  it("acepta una ruta interna con query y hash", () => {
    expect(safeNextPath("/app/knowledge?tab=ask#x")).toBe("/app/knowledge?tab=ask#x");
  });

  it("sin parámetro usa la ruta por defecto", () => {
    expect(safeNextPath(null)).toBe(DEFAULT_AFTER_LOGIN);
    expect(safeNextPath(undefined)).toBe(DEFAULT_AFTER_LOGIN);
    expect(safeNextPath("")).toBe(DEFAULT_AFTER_LOGIN);
  });

  it.each([
    "https://phishing.example",
    "http://phishing.example/app",
    "//phishing.example",
    "/\\phishing.example",
    "\\\\phishing.example",
    "javascript:alert(1)",
    "app/continuity",
    " /app",
    "/\t/phishing.example",
    "/%2F%2Fphishing.example",
    "/%5Cphishing.example",
  ])("rechaza %s", (value) => {
    expect(safeNextPath(value)).toBe(DEFAULT_AFTER_LOGIN);
  });

  it("respeta un fallback explícito", () => {
    expect(safeNextPath("//x", "/app")).toBe("/app");
  });
});
