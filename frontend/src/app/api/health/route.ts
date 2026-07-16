import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest) {
  // El backend de producción solo monta el router /v2 (asgi.py); /health raíz no existe.
  return proxyToBackend(request, "/v2/health", { method: "GET" });
}

export const maxDuration = 60;
