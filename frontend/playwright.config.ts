import { defineConfig, devices } from "@playwright/test";

/**
 * E2E del recorrido de la demo (docs/demo/guion.md) contra un despliegue real.
 * Por defecto, producción: lo que importa es que la demo funcione donde la ve el
 * jurado. E2E_BASE_URL apunta a un preview o a `next start` local.
 */
export default defineConfig({
  testDir: "./e2e",
  // El backend de la demo duerme en plan gratuito: la primera petición puede tardar.
  timeout: 120_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://mnemo-beta-one.vercel.app",
    locale: "es-ES",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
