import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToBackend(
    request,
    `/v2/knowledge/${encodeURIComponent(id)}${request.nextUrl.search}`,
    { method: "GET" },
  );
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/knowledge/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body,
    contentType: "application/json",
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  return proxyToBackend(
    request,
    `/v2/knowledge/${encodeURIComponent(id)}${request.nextUrl.search}`,
    { method: "DELETE" },
  );
}

export const maxDuration = 60;
