import type { NextConfig } from "next";

/**
 * Cabeceras de seguridad para todas las rutas. Sin CSP completa a propósito: la app
 * carga Supabase y los scripts de Next, y una política mal ajustada la rompería; se
 * ponen las de riesgo cero. `frame-ancestors 'none'` + X-Frame-Options impiden
 * incrustar la app (y el sello de /verify) en otra página para engañar con clics.
 */
export const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
