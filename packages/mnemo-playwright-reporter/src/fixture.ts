import { test as base } from "@playwright/test";

/** Override del fixture `page`: captura el DOM en el teardown SOLO para tests que usan página
 *  (no fuerza navegador en tests que no la usan). Failure-safe: nunca rompe el test. */
export const test = base.extend({
  page: async ({ page }, use, testInfo) => {
    await use(page);
    try {
      const html = await page.content();
      await testInfo.attach("__mnemo_dom__", { body: Buffer.from(html), contentType: "text/html" });
    } catch {
      // No romper el test si la página ya no está disponible.
    }
  },
});

export { expect } from "@playwright/test";
