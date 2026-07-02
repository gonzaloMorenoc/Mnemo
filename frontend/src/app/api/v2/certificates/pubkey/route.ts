import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

// PÚBLICO: clave pública de firma para verificar actas offline, sin cuenta.
export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/v2/certificates/pubkey", { method: "GET" });
}

export const maxDuration = 60;
