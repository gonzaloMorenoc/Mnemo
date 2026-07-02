import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

// PÚBLICO: la verificación es cripto pura; el proxy solo reenvía Authorization
// si viene, así que funciona sin sesión (un tercero verifica sin cuenta).
export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxyToBackend(request, "/v2/certificates/verify", {
    method: "POST",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
