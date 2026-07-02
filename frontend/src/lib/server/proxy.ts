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

/**
 * Passthrough para respuestas binarias (p.ej. PDF): no intenta parsear JSON,
 * reenvía el cuerpo y preserva Content-Type / Content-Disposition. En error
 * del backend devuelve el JSON de error tal cual.
 */
export async function proxyBinaryToBackend(request: NextRequest, endpoint: string) {
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

  try {
    const response = await fetch(`${apiBaseUrl}${endpoint}`, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    if (!response.ok) {
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
    }

    const outHeaders = new Headers();
    const contentType = response.headers.get("content-type");
    const disposition = response.headers.get("content-disposition");
    if (contentType) outHeaders.set("Content-Type", contentType);
    if (disposition) outHeaders.set("Content-Disposition", disposition);

    return new NextResponse(await response.arrayBuffer(), {
      status: response.status,
      headers: outHeaders,
    });
  } catch {
    return NextResponse.json(
      { detail: "Could not reach backend API. Check NEXT_PUBLIC_API_BASE_URL." },
      { status: 502 },
    );
  }
}
