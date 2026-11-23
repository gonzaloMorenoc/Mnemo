import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ org_id: string }> },
) {
  const { org_id } = await params;
  return proxyToBackend(request, `/v2/orgs/${encodeURIComponent(org_id)}/members`, {
    method: "GET",
  });
}

export const maxDuration = 60;
