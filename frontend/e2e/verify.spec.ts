import { expect, test } from "@playwright/test";

import { ACTA_TRASPASO_HASH, contenidoDe, manipular } from "./acta";

/**
 * Acto 2 del guion: el acta de traspaso se abre en otro dispositivo, sin sesión.
 * Es la parte pública de la demo: no necesita credenciales.
 */
test.describe("/verify — acta de traspaso por enlace, sin cuenta", () => {
  test("el enlace de la demo muestra el SELLO DE TRASPASO con lo que se firmó", async ({ page }) => {
    const acta = contenidoDe(ACTA_TRASPASO_HASH);
    await page.goto(`/verify${ACTA_TRASPASO_HASH}`);

    await expect(page.getByText("Acta de traspaso auténtica · firmada · íntegra")).toBeVisible();
    await expect(page.getByText(String(acta.project), { exact: true })).toBeVisible();
    await expect(page.getByText("María (QA senior)", { exact: true })).toBeVisible();
    await expect(page.getByText("Pablo", { exact: true })).toBeVisible();
    await expect(page.getByText(/26 elementos de conocimiento depositados/)).toBeVisible();
    await expect(page.getByText("85", { exact: true })).toBeVisible();
  });

  test("el mismo enlace con el índice retocado da «Firma NO válida»", async ({ page }) => {
    const acta = contenidoDe(ACTA_TRASPASO_HASH);
    const continuity = { ...(acta.continuity as Record<string, unknown>), score: 99 };
    await page.goto(`/verify${manipular(ACTA_TRASPASO_HASH, { continuity })}`);

    await expect(page.getByRole("alert").getByText("Firma NO válida")).toBeVisible();
    await expect(page.getByText("Acta de traspaso auténtica · firmada · íntegra")).toHaveCount(0);
  });

  test("un enlace cortado al copiarlo lo explica, sin dar la firma por mala", async ({ page }) => {
    await page.goto(`/verify${ACTA_TRASPASO_HASH.slice(0, 200)}`);

    await expect(page.getByText(/Este enlace está incompleto/)).toBeVisible();
    await expect(page.getByText("Firma NO válida")).toHaveCount(0);
  });
});
