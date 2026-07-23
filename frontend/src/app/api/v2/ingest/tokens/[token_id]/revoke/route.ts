import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ token_id: string }> },
) {
  const { token_id } = await params;
  return proxyToBackend(
    request,
    `/v2/ingest/tokens/${encodeURIComponent(token_id)}/revoke`,
    { method: "POST" },
  );
}

export const maxDuration = 60;
