import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const org_id = request.nextUrl.searchParams.get("org_id") ?? "";
  return proxyToBackend(request, `/v2/repo/tests?org_id=${encodeURIComponent(org_id)}`, {
    method: "GET",
  });
}

export const maxDuration = 60;
