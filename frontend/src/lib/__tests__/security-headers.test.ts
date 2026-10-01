import { describe, expect, it } from "vitest";

import nextConfig, { SECURITY_HEADERS } from "../../../next.config";

describe("cabeceras de seguridad", () => {
  it("se aplican a todas las rutas e impiden incrustar la app en otra página", async () => {
    const rules = await nextConfig.headers!();
    expect(rules).toEqual([{ source: "/:path*", headers: SECURITY_HEADERS }]);
    const byKey = Object.fromEntries(SECURITY_HEADERS.map((h) => [h.key, h.value]));
    expect(byKey["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
    expect(byKey["X-Frame-Options"]).toBe("DENY");
    expect(byKey["X-Content-Type-Options"]).toBe("nosniff");
  });
});
