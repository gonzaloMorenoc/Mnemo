import { NextResponse, type NextRequest } from "next/server";

import { getPublicEnv } from "@/lib/env";

// Menor que maxDuration (60s) de los route handlers: así el proxy devuelve un
// error CLARO antes de que Vercel mate la función con un 504 opaco. Ajustable
// por llamada para rutas legítimamente lentas (LLM).
const DEFAULT_TIMEOUT_MS = 55_000;

function notConfigured() {
  return NextResponse.json(
    { detail: "NEXT_PUBLIC_API_BASE_URL is not configured." },
    { status: 500 },
  );
}

function isTimeout(err: unknown): boolean {
  return err instanceof DOMException && err.name === "TimeoutError";
}

// Convierte un fallo del fetch en una respuesta clara: 504 si expiró el tiempo
// (backend lento / arrancando en frío), 502 si es inalcanzable.
function backendError(err: unknown) {
  if (isTimeout(err)) {
    return NextResponse.json(
      {
        detail:
          "El servicio tardó demasiado en responder (puede estar iniciándose). Reinténtalo en unos segundos.",
      },
      { status: 504 },
    );
  }
  return NextResponse.json(
    { detail: "No pudimos contactar con el servicio. Reinténtalo en unos segundos." },
    { status: 502 },
  );
}

function authHeaders(request: NextRequest, contentType?: string): Headers {
  const headers = new Headers();
  const authHeader = request.headers.get("authorization");
  if (authHeader) {
    headers.set("Authorization", authHeader);
  }
  if (contentType) {
    headers.set("Content-Type", contentType);
  }
  return headers;
}

export async function proxyToBackend(
  request: NextRequest,
  endpoint: string,
  init: {
    method: "GET" | "POST" | "PATCH" | "DELETE";
    body?: BodyInit;
    contentType?: string;
    timeoutMs?: number;
  },
) {
  const { apiBaseUrl } = getPublicEnv();
  if (!apiBaseUrl) return notConfigured();

  try {
    const response = await fetch(`${apiBaseUrl}${endpoint}`, {
      method: init.method,
      headers: authHeaders(request, init.contentType),
      body: init.body,
      cache: "no-store",
      signal: AbortSignal.timeout(init.timeoutMs ?? DEFAULT_TIMEOUT_MS),
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
  } catch (err) {
    return backendError(err);
  }
}

/**
 * Passthrough para respuestas binarias (p.ej. PDF): no intenta parsear JSON,
 * reenvía el cuerpo y preserva Content-Type / Content-Disposition. En error
 * del backend devuelve el JSON de error tal cual.
 */
export async function proxyBinaryToBackend(
  request: NextRequest,
  endpoint: string,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
) {
  const { apiBaseUrl } = getPublicEnv();
  if (!apiBaseUrl) return notConfigured();

  try {
    const response = await fetch(`${apiBaseUrl}${endpoint}`, {
      method: "GET",
      headers: authHeaders(request),
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
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
  } catch (err) {
    return backendError(err);
  }
}
