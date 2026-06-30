import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  return proxyToBackend(request, "/v2/ingest/report", { method: "POST", body: formData });
}

export const maxDuration = 60;
