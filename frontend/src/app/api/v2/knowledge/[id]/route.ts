import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToBackend(
    request,
    `/v2/knowledge/${encodeURIComponent(id)}${request.nextUrl.search}`,
    { method: "GET" },
  );
}

export const maxDuration = 60;
