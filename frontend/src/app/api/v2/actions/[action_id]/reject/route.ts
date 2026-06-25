import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ action_id: string }> }) {
  const { action_id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/actions/${encodeURIComponent(action_id)}/reject`,
    { method: "POST", body, contentType: "application/json" });
}
