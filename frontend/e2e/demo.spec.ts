import { expect, test, type Page } from "@playwright/test";

/**
 * Actos 1 y 3 del guion (docs/demo/guion.md), con sesión: lo que el jurado ve
 * dentro de la app. SOLO LEE: no emite actas ni escribe nada en la demo.
 *
 * Necesita E2E_EMAIL y E2E_PASSWORD (mejor una cuenta de solo lectura). Sin
 * ellas se salta: la parte pública (verify.spec.ts) sigue corriendo.
 */
const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;
const ORG = process.env.E2E_ORG ?? "Demo MTP";

test.skip(!EMAIL || !PASSWORD, "Sin E2E_EMAIL/E2E_PASSWORD: se omite el recorrido con sesión");

async function entrar(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL!);
  await page.getByLabel("Contraseña").fill(PASSWORD!);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await page.waitForURL(/\/app/);
  // Con varias organizaciones hay un selector; con una sola, un enlace con su nombre.
  const selector = page.getByRole("combobox", { name: "Organización" });
  if (await selector.isVisible()) {
    await selector.click();
    await page.getByRole("option", { name: ORG, exact: true }).click();
  } else {
    await expect(page.getByText(ORG, { exact: true }).first()).toBeVisible();
  }
}

function filaDelMapa(page: Page, proyecto: string) {
  return page.locator("li", {
    has: page.getByTestId("proyecto").getByText(proyecto, { exact: true }),
  });
}

test.describe.configure({ mode: "serial" });

test("Acto 1 · el mapa de riesgo separa checkout-suite (85) de banca-movil (25)", async ({ page }) => {
  await entrar(page);
  await page.goto("/app/continuity");

  await expect(filaDelMapa(page, "checkout-suite")).toContainText("85");
  await expect(filaDelMapa(page, "banca-movil")).toContainText("25");
});

test("Acto 2 · el acta de checkout-suite sigue íntegra con lo depositado", async ({ page }) => {
  await entrar(page);
  await page.goto("/app/continuity?project=checkout-suite");

  await expect(page.getByText(/Lo depositado sigue intacto/)).toBeVisible();
  await expect(page.getByText(/El conocimiento ha cambiado desde el acta/)).toHaveCount(0);
});

test("Acto 3 · la pregunta del guion responde con el LLM y cita a Pagos", async ({ page }) => {
  await entrar(page);
  await page.goto("/app/knowledge");
  await page.getByRole("tab", { name: "Preguntar" }).click();
  await page.getByPlaceholder(/¿Qué quieres saber\?/).fill("¿A quién pregunto por el sandbox del PSP?");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();

  const respuesta = page.getByText("Respuesta", { exact: true }).locator("xpath=following-sibling::p[1]");
  await expect(respuesta).toBeVisible();
  // «LLM no accesible» = la IA degradó: la demo enseñaría fuentes sueltas, no una respuesta.
  await expect(respuesta).not.toContainText("LLM no accesible");
  await expect(respuesta).toContainText(/Pagos/i);
});
