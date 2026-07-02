import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToBackend(
    request,
    `/v2/defects/${encodeURIComponent(id)}/root-cause${request.nextUrl.search}`,
    { method: "POST" },
  );
}

export const maxDuration = 60;
