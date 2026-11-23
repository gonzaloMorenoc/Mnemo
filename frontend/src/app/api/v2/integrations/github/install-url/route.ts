import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export const dynamic = "force-dynamic";

// Inicio de la vinculación de la GitHub App: el backend devuelve la URL de
// instalación con un `state` firmado (org + usuario, caduca en 10 min).
export async function GET(request: NextRequest) {
  const org_id = request.nextUrl.searchParams.get("org_id") ?? "";
  return proxyToBackend(
    request,
    `/v2/integrations/github/install-url?org_id=${encodeURIComponent(org_id)}`,
    { method: "GET" },
  );
}
