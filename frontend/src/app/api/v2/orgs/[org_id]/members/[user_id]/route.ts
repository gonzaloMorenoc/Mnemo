import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

type Params = { params: Promise<{ org_id: string; user_id: string }> };

function memberPath(orgId: string, userId: string) {
  return `/v2/orgs/${encodeURIComponent(orgId)}/members/${encodeURIComponent(userId)}`;
}

export async function PATCH(request: NextRequest, { params }: Params) {
  const { org_id, user_id } = await params;
  const body = await request.text();
  return proxyToBackend(request, memberPath(org_id, user_id), {
    method: "PATCH",
    body,
    contentType: "application/json",
  });
}

export async function DELETE(request: NextRequest, { params }: Params) {
  const { org_id, user_id } = await params;
  return proxyToBackend(request, memberPath(org_id, user_id), { method: "DELETE" });
}

export const maxDuration = 60;
