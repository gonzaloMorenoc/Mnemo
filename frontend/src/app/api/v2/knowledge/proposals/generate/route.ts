import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest) {
  const body = await request.text();
  return proxyToBackend(request, "/v2/knowledge/proposals/generate", {
    method: "POST",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
