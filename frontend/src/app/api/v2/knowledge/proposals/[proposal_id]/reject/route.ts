import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ proposal_id: string }> },
) {
  const { proposal_id } = await params;
  const body = await request.text();
  return proxyToBackend(
    request,
    `/v2/knowledge/proposals/${encodeURIComponent(proposal_id)}/reject`,
    { method: "POST", body, contentType: "application/json" },
  );
}

export const maxDuration = 60;
