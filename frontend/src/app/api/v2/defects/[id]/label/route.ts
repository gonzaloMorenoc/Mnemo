import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/server/proxy";

// Slug `[id]` (no `[family_id]`): Next.js exige un único nombre de slug por
// posición; tener `defects/[id]` y `defects/[family_id]` a la vez crashea el
// runtime entero ("cannot use different slug names for the same dynamic path").
export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();
  return proxyToBackend(request, `/v2/defects/${encodeURIComponent(id)}/label`,
    { method: "PATCH", body, contentType: "application/json" });
}

export const maxDuration = 60;
