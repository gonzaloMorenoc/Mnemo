import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const org_id = request.nextUrl.searchParams.get("org_id") ?? "";
  return proxyToBackend(request, `/v2/integrations/github?org_id=${encodeURIComponent(org_id)}`, {
    method: "GET",
  });
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxyToBackend(request, "/v2/integrations/github", {
    method: "POST",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
