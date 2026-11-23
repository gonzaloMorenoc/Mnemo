import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export const dynamic = "force-dynamic";

function backendPath(orgId: string) {
  return `/v2/orgs/${encodeURIComponent(orgId)}/llm-settings`;
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = await params;
  return proxyToBackend(request, backendPath(orgId), { method: "GET" });
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = await params;
  const body = await request.text();
  return proxyToBackend(request, backendPath(orgId), {
    method: "PUT",
    body,
    contentType: "application/json",
  });
}

export const maxDuration = 60;
