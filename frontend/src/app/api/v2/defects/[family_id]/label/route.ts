import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ family_id: string }> }) {
  const { family_id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/defects/${encodeURIComponent(family_id)}/label`,
    { method: "PATCH", body, contentType: "application/json" });
}

export const maxDuration = 60;
