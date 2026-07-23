import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ proposal_id: string }> },
) {
  const { proposal_id } = await params;
  return proxyToBackend(
    request,
    `/v2/knowledge/proposals/${encodeURIComponent(proposal_id)}/refine`,
    { method: "POST" },
  );
}

export const maxDuration = 60;
