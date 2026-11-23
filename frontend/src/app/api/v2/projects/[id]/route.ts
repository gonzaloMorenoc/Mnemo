import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/projects/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
