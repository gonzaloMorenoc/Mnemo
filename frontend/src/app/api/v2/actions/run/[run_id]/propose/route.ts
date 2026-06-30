import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/server/proxy";

export async function POST(request: NextRequest, { params }: { params: Promise<{ run_id: string }> }) {
  const { run_id } = await params;
  return proxyToBackend(request, `/v2/actions/run/${encodeURIComponent(run_id)}/propose`, { method: "POST" });
}

export const maxDuration = 60;
