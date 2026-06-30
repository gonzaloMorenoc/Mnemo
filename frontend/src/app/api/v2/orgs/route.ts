import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/v2/orgs", { method: "GET" });
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxyToBackend(request, "/v2/orgs", {
    method: "POST",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
