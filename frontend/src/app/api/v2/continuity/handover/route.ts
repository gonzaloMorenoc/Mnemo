import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/v2/continuity/handover", { method: "POST" });
}

export const maxDuration = 60;
