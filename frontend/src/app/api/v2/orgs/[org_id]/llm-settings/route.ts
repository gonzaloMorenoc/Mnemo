import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export const dynamic = "force-dynamic";

function backendPath(org_id: string) {
  return `/v2/orgs/${encodeURIComponent(org_id)}/llm-settings`;
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ org_id: string }> }) {
  const { org_id } = await params;
  return proxyToBackend(request, backendPath(org_id), { method: "GET" });
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ org_id: string }> }) {
  const { org_id } = await params;
  const body = await request.text();
  return proxyToBackend(request, backendPath(org_id), {
    method: "PUT",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
