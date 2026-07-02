import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, `/v2/graph/gaps${request.nextUrl.search}`, { method: "GET" });
}

export const maxDuration = 60;
