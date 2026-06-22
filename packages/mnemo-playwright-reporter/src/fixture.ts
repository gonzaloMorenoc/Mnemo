import { test as base } from "@playwright/test";

/** Auto-fixture: tras cada test captura el DOM de la página y lo adjunta para el reporter. */
export const test = base.extend<{ mnemoDom: void }>({
  mnemoDom: [
    async ({ page }, use, testInfo) => {
      await use();
      try {
        const html = await page.content();
        await testInfo.attach("mnemo-dom", { body: Buffer.from(html), contentType: "text/html" });
      } catch {
        // No romper el test si la página ya no está disponible.
      }
    },
    { auto: true },
  ],
});

export { expect } from "@playwright/test";
