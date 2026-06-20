import { NextResponse, type NextRequest } from "next/server";

import { getPublicEnv } from "@/lib/env";

export async function proxyToBackend(
  request: NextRequest,
  endpoint: string,
  init: {
    method: "GET" | "POST" | "PATCH" | "DELETE";
    body?: BodyInit;
    contentType?: string;
  },
) {
  const { apiBaseUrl } = getPublicEnv();

  if (!apiBaseUrl) {
    return NextResponse.json(
      { detail: "NEXT_PUBLIC_API_BASE_URL is not configured." },
      { status: 500 },
    );
  }

  const headers = new Headers();
  const authHeader = request.headers.get("authorization");
  if (authHeader) {
    headers.set("Authorization", authHeader);
  }
  if (init.contentType) {
    headers.set("Content-Type", init.contentType);
  }

  try {
    const response = await fetch(`${apiBaseUrl}${endpoint}`, {
      method: init.method,
      headers,
      body: init.body,
      cache: "no-store",
    });

    const text = await response.text();
    let payload: unknown = null;

    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { detail: text };
      }
    }

    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Could not reach backend API. Check NEXT_PUBLIC_API_BASE_URL." },
      { status: 502 },
    );
  }
}
